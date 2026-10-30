# -*- coding: utf8 -*-

import importlib.util
import json
import os
import sys
import types
import uuid

from unittest.mock import MagicMock

import flask_jwt_extended
import pytest
from flask import Flask, g

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# backend#440 (b): opening an instance pops 3 mobs, each announced to the AI.
# The AI listens on ai-creature-<env> (PS_AI_CREATURE) and reads
# json.loads(data)['action'], then json.loads(data['creature']) again.
# The route used to publish on the bare 'ai-creature' channel with a
# double-serialised payload, so the mobs never got an AI thread.
# Pure unit test: no Mongo, no Redis.
INSTANCE_ROUTES = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'instance')
UTILS_PATH = os.path.join(LOCAL_PATH, 'utils')

PS_AI_CREATURE = 'ai-creature-test'
CREATURE_ID = uuid.uuid4()
INSTANCE_ID = uuid.uuid4()
MAP_ID = 1
INSTANCE_JSON = json.dumps({"_id": str(INSTANCE_ID), "map": MAP_ID})
MOBS_NUMBER = 3
BODY = {"hardcore": False, "fast": False, "mapid": MAP_ID, "public": True}
RACE = {
    'name': 'Mob', 'min_m': 10, 'min_r': 10, 'min_g': 10,
    'min_v': 10, 'min_p': 10, 'min_b': 10,
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


class _Embedded:
    """ Stands for the mongoengine embedded documents: keeps its kwargs. """
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _InstanceDocument(_Embedded):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = INSTANCE_ID

    def save(self):
        pass

    def to_json(self, json_options=None):
        return INSTANCE_JSON

    def to_mongo(self):
        return {"_id": str(INSTANCE_ID)}


class _CreatureDocument(_Embedded):
    """ Every popped mob is recorded, its to_json is a known string. """
    DoesNotExist = type('DoesNotExist', (Exception,), {})
    popped = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.popped.append(self)

    def save(self):
        pass

    def to_json(self, json_options=None):
        return json.dumps({"_id": str(self._id), "name": self.name})


@pytest.fixture
def route(monkeypatch):
    """
    Loads add.py straight from its file with every Mongo / Redis / Discord
    dependency stubbed. cput is a MagicMock recording each publish.
    """
    _CreatureDocument.popped = []
    the_map = types.SimpleNamespace(id=MAP_ID, data={'width': 10, 'height': 10})

    _module(
        'mongo.models.Creature', monkeypatch,
        CreatureDocument=_CreatureDocument,
        CreatureHP=_Embedded,
        CreatureSlots=_Embedded,
        CreatureStats=_Embedded,
        CreatureStatsType=_Embedded,
        CreatureSquad=_Embedded,
        CreatureKorp=_Embedded,
        )
    _module('mongo.models.Instance', monkeypatch, InstanceDocument=_InstanceDocument)
    _module(
        'mongo.models.Meta', monkeypatch,
        MetaMap=types.SimpleNamespace(
            objects=lambda **kwargs: types.SimpleNamespace(get=lambda: the_map),
            ),
        )
    _module('mongo.utils', monkeypatch, JSON_OPTIONS=None, utcnow=lambda: None)
    _module('routes.mypc.instance._tools', monkeypatch, get_empty_coords=lambda: (1, 1))
    _module(
        'utils.decorators', monkeypatch,
        check_creature_exists=_identity,
        check_is_json=_identity,
        )
    _module('utils.discord', monkeypatch, discord_scopes=lambda creature: [])
    _module('utils.redis', monkeypatch, cput=None, qput=lambda queue, msg: None)
    _module(
        'variables', monkeypatch,
        # Read by the real utils/redis.py at load (lazy pool, never connects)
        env_vars={'REDIS_HOST': '127.0.0.1', 'REDIS_PORT': 6379, 'REDIS_BASE': 0},
        metaIndexed={'race': {raceid: RACE for raceid in range(11, 17)}},
        PS_AI_CREATURE=PS_AI_CREATURE,
        YQ_DISCORD='yq-discord-test',
        )
    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    module = _load('test_instance_add_route', os.path.join(INSTANCE_ROUTES, 'add.py'))
    monkeypatch.setattr(module, 'cput', MagicMock())
    return module


def _open_instance(route):
    creature = types.SimpleNamespace(
        id=CREATURE_ID,
        instance=None,
        name='PyTest',
        updated=None,
        x=None,
        y=None,
        save=lambda: None,
        )
    with Flask(__name__).test_request_context(json=BODY):
        g.h = f'[Creature.id:{CREATURE_ID}]'
        g.Creature = creature
        response, code = route.add(creatureuuid=CREATURE_ID)
        return code, response.get_json()


def test_instance_add_publishes_one_pop_per_mob_on_the_ai_channel(route):
    code, body = _open_instance(route)

    assert code == 201
    assert body['success'] is True
    assert len(_CreatureDocument.popped) == MOBS_NUMBER
    assert route.cput.call_count == MOBS_NUMBER
    channels = [call.args[0] for call in route.cput.call_args_list]
    assert channels == [PS_AI_CREATURE] * MOBS_NUMBER
    assert 'ai-creature' not in channels


def test_instance_add_pop_payload_is_a_dict_with_the_ai_contract(route):
    _open_instance(route)

    payloads = [call.args[1] for call in route.cput.call_args_list]
    assert len(payloads) == MOBS_NUMBER
    for payload, mob in zip(payloads, _CreatureDocument.popped):
        assert isinstance(payload, dict)
        assert set(payload) == {'action', 'instance', 'creature'}
        assert payload['action'] == 'pop'
        # Kept as JSON strings: the AI json.loads them again (ai/utils/actions.py)
        assert payload['instance'] == INSTANCE_JSON
        assert payload['creature'] == mob.to_json()


def test_instance_add_pop_is_readable_by_the_ai_through_the_real_cput(route, monkeypatch):
    """ The published string, json.loads'ed once as the AI does, gives action 'pop'. """
    redis_utils = _load('test_instance_add_real_redis', os.path.join(UTILS_PATH, 'redis.py'))
    publish = MagicMock()
    monkeypatch.setattr(redis_utils, 'r', types.SimpleNamespace(publish=publish))
    monkeypatch.setattr(route, 'cput', redis_utils.cput)

    _open_instance(route)

    assert publish.call_count == MOBS_NUMBER
    for call, mob in zip(publish.call_args_list, _CreatureDocument.popped):
        channel, data = call.args
        assert channel == PS_AI_CREATURE
        message = json.loads(data)
        assert message['action'] == 'pop'
        assert json.loads(message['creature'])['_id'] == str(mob._id)
