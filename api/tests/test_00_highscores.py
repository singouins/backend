# -*- coding: utf8 -*-

import datetime
import importlib.util
import os
import sys
import types
import uuid

import flask_jwt_extended
import mongoengine
import mongomock
import pytest
from flask import Flask, g
from loguru import logger

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# GET /mypc/<uuid>/highscores, Lordslair 2026-10-30 (#engine-api msg
# 1565832626781290527): a load error answers a generic message (the exception
# is logged, never sent), and Highscore.internal is never sent to the player.
# Unit test: no Redis, the Highscores are raw documents on an in-memory
# mongomock read through the real model, so a document the model cannot load
# raises for real. The tests never depend on the Highscore.internal shape.
REPO_PATH = os.path.join(LOCAL_PATH, os.pardir)
HIGHSCORE_MODEL = os.path.join(REPO_PATH, 'mongo', 'models', 'Highscore.py')
MONGO_UTILS = os.path.join(REPO_PATH, 'mongo', 'utils.py')
MOCK_ALIAS = 'test-highscores'
HIGHSCORES_ROUTE = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'highscores.py')

STAMP = datetime.datetime(2026, 10, 30, 12, 0, 0)
# Flask serializes a datetime as an HTTP date
STAMP_JSON = 'Fri, 30 Oct 2026 12:00:00 GMT'
# Never read by the route: any shape, including one the model does not know
OPAQUE = {'secret_counter': {'value': 42}}
PUBLIC = {
    'general': {'death': 3, 'kill': 7},
    'profession': {'mining': 2},
    }


def _identity(func):
    return func


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(name, monkeypatch, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def mongo():
    """
    In-memory Mongo on its own alias, dropped after the test: in CI the
    default alias may already point at the real Mongo, registered by another
    test importing the mongo package.
    """
    mongoengine.connect(
        'pytest', alias=MOCK_ALIAS, mongo_client_class=mongomock.MongoClient,
        uuidRepresentation='standard',
        )
    yield
    # mongomock keeps its data while any client lives: drop it explicitly
    mongoengine.connection.get_connection(MOCK_ALIAS).drop_database('pytest')
    mongoengine.disconnect(alias=MOCK_ALIAS)


@pytest.fixture
def world(mongo, monkeypatch):
    """
    Loads highscores.py straight from its file (the mongo and routes.mypc
    packages connect / pull every route at import) with the real Highscore
    model. The decorators are stubbed: the view runs with g already set, as
    they would. Every log line the route writes lands in `logs`.
    """
    # Highscore.py imports mongo.utils: give it the real file under a stub mongo
    # package, so mongo/__init__.py (and its connect()) never runs
    package = _module('mongo', monkeypatch)
    package.__path__ = []
    monkeypatch.setitem(sys.modules, 'mongo.utils', _load('mongo.utils', MONGO_UTILS))
    model = _load('test_highscores_model', HIGHSCORE_MODEL)
    model.HighscoreDocument._meta['db_alias'] = MOCK_ALIAS
    monkeypatch.setitem(sys.modules, 'mongo.models.Highscore', model)
    _module('utils.decorators', monkeypatch, check_creature_exists=_identity)
    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    route = _load('test_highscores_route', HIGHSCORES_ROUTE)
    app = Flask(__name__)
    collection = model.HighscoreDocument._get_collection()

    logs = []
    sink = logger.add(lambda message: logs.append(str(message)), level='DEBUG')

    def store(**fields):
        """ Inserts a raw Highscore: the PUBLIC fields, overridden by fields. """
        creatureuuid = uuid.uuid4()
        collection.insert_one({
            '_id': str(creatureuuid),
            'created': STAMP,
            'updated': STAMP,
            'internal': {},
            **PUBLIC,
            **fields,
            })
        return creatureuuid

    def get(creatureuuid):
        with app.test_request_context():
            g.h = f'[Creature.id:{creatureuuid}]'
            response, code = route.highscores_get(creatureuuid=creatureuuid)
            return code, response.get_json()

    yield types.SimpleNamespace(model=model, store=store, get=get, logs=logs)
    logger.remove(sink)


def test_highscores_do_not_send_internal(world):
    creatureuuid = world.store(internal=OPAQUE)

    code, body = world.get(creatureuuid)

    assert code == 200
    assert body['success'] is True
    assert 'internal' not in body['payload']


def test_highscores_send_the_public_fields_unchanged(world):
    creatureuuid = world.store(internal=OPAQUE)

    code, body = world.get(creatureuuid)

    payload = body['payload']
    assert set(payload) == {'_id', 'created', 'general', 'profession', 'updated'}
    assert payload['_id'] == str(creatureuuid)
    assert payload['created'] == STAMP_JSON
    assert payload['updated'] == STAMP_JSON
    # The model fills what the raw document lacks with its defaults
    assert payload['general'] == world.model.HighscoreGeneral(
        **PUBLIC['general']).to_mongo().to_dict()
    assert payload['profession'] == world.model.HighscoreProfession(
        **PUBLIC['profession']).to_mongo().to_dict()


def test_highscores_answer_whatever_the_internal_shape(world):
    # Unknown to the model: it would raise FieldDoesNotExist if it were loaded
    for internal in [{}, OPAQUE, {'shard': {'bought': 1}}, {'shard': {'broken': {'used': 1}}}]:
        creatureuuid = world.store(internal=internal)

        code, body = world.get(creatureuuid)

        assert code == 200
        assert body['success'] is True
        assert 'internal' not in body['payload']


def test_highscores_load_error_answers_a_generic_message(world):
    # A public field the model does not know: the load raises FieldDoesNotExist
    creatureuuid = world.store(general={'secret_counter': 42})

    code, body = world.get(creatureuuid)

    assert code == 200
    assert body['success'] is False
    assert body['payload'] is None
    assert body['msg'] == f'[Creature.id:{creatureuuid}] HighscoreDocument Query KO'


def test_highscores_load_error_is_logged_server_side(world):
    creatureuuid = world.store(general={'secret_counter': 42})

    world.get(creatureuuid)

    errors = [line for line in world.logs if 'HighscoreDocument Query KO [' in line]
    assert len(errors) == 1
    # The log carries the exception text: a reason between the brackets
    assert errors[0].split('Query KO [', 1)[1].split(']', 1)[0].strip()


def test_highscores_not_found(world):
    creatureuuid = uuid.uuid4()

    code, body = world.get(creatureuuid)

    assert code == 200
    assert body['success'] is False
    assert body['payload'] is None
