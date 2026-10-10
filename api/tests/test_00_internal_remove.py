# -*- coding: utf8 -*-

import datetime
import importlib.util
import json
import os
import sys
import types
import uuid

import pytest
from flask import Flask

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# Designer ruling Q99 (2026-10-10): a dead monster is removed from the map at
# once. The fight resolver calls POST /internal/instance/<i>/creature/<c>/remove,
# which removes the monster as an instance close does (AI kill on the env
# channel, Redis keys purged, Creature deleted last). The AI listens on
# ai-creature-<env>, so every kill, the instance-close one too, goes there.
# Pure unit test: no Mongo, no Redis.

TOKEN = 'unit-test-token'
PS_AI_CREATURE = 'ai-creature-pytest'
INSTANCE_ID = uuid.uuid4()
OTHER_INSTANCE_ID = uuid.uuid4()
MONSTER_ID = uuid.uuid4()
SINGOUIN_ID = uuid.uuid4()

# Same stubbing as test_00_internal_eject_notice.py: routes.internal.instance
# imports the Mongo models (directly and through utils.decorators /
# utils.instance), and the real mongo package connects at import
MODEL_STUBS = {
    'mongo.models.Creature': ['CreatureDocument'],
    'mongo.models.Instance': ['InstanceDocument'],
    'mongo.models.Item': ['ItemDocument'],
    'mongo.models.Korp': ['KorpDocument'],
    'mongo.models.Squad': ['SquadDocument'],
    'mongo.models.User': ['UserDocument'],
    }
ISOLATED = [
    'routes.internal',
    'routes.internal.instance',
    'utils.decorators',
    'utils.instance',
    ]
_ABSENT = object()


@pytest.fixture
def modules(monkeypatch):
    """
    Imports routes.internal.instance and utils.instance against stubbed models,
    then drops them (and puts any previous copy back). Inside api/tests,
    `variables` is tests/variables.py, so the names read at import are set there.
    """
    variables = sys.modules['variables']
    monkeypatch.setattr(variables, 'SEP_INTERNAL_TOKEN', TOKEN, raising=False)
    monkeypatch.setattr(variables, 'YQ_DISCORD', 'pytest:yarqueue:discord', raising=False)
    monkeypatch.setattr(variables, 'PS_AI_CREATURE', PS_AI_CREATURE, raising=False)
    # Same keys as api/variables.py: utils.redis builds its (lazy) pool from them at import
    monkeypatch.setattr(variables, 'env_vars', {
        'API_ENV': 'pytest',
        'REDIS_HOST': '127.0.0.1',
        'REDIS_PORT': 6379,
        'REDIS_BASE': 0,
        }, raising=False)

    for name, attributes in MODEL_STUBS.items():
        stub = types.ModuleType(name)
        for attribute in attributes:
            setattr(stub, attribute, None)
        monkeypatch.setitem(sys.modules, name, stub)

    saved = {}
    for name in ISOLATED:
        parent, _, child = name.rpartition('.')
        parent_module = sys.modules.get(parent)
        attribute = _ABSENT if parent_module is None else getattr(parent_module, child, _ABSENT)
        saved[name] = (sys.modules.pop(name, None), attribute)
    try:
        import routes.internal.instance as route
        import utils.instance as utils_instance
        yield types.SimpleNamespace(route=route, utils_instance=utils_instance)
    finally:
        for name, (previous, _) in saved.items():
            sys.modules.pop(name, None)
            if previous is not None:
                sys.modules[name] = previous
        for name, (_, attribute) in saved.items():
            parent, _, child = name.rpartition('.')
            parent_module = sys.modules.get(parent)
            if parent_module is None:
                continue
            if attribute is _ABSENT:
                if hasattr(parent_module, child):
                    delattr(parent_module, child)
            else:
                setattr(parent_module, child, attribute)


class _Collection:
    """ Stands for Document.objects: objects(_id=x).first() reads a dict by id. """
    def __init__(self, documents):
        self.documents = documents

    def __call__(self, _id=None, **kwargs):
        return types.SimpleNamespace(first=lambda: self.documents.get(_id))


def _document(events, store, _id, instance, account=None, delete_error=None):
    """ A Creature: delete() records the call and drops it from the store. """
    def delete():
        if delete_error is not None:
            raise delete_error
        events.append(('delete', _id))
        store.pop(_id, None)
    return types.SimpleNamespace(
        id=_id,
        account=account,
        instance=instance,
        to_json=lambda: json.dumps({"_id": str(_id), "name": 'Monster'}),
        delete=delete,
        )


@pytest.fixture
def world(modules, monkeypatch):
    """
    Runs the remove view on a minimal Flask app. Creatures and Instances live
    in dicts; cput(), purge_creature_keys() and Creature.delete() append to
    `events` in call order.
    """
    route = modules.route
    events = []
    creatures = {}
    instances = {
        INSTANCE_ID: types.SimpleNamespace(
            id=INSTANCE_ID,
            to_json=lambda: json.dumps({"_id": str(INSTANCE_ID)}),
            ),
        }
    monkeypatch.setattr(route, 'CreatureDocument', types.SimpleNamespace(objects=_Collection(creatures)))  # noqa: E501
    monkeypatch.setattr(route, 'InstanceDocument', types.SimpleNamespace(objects=_Collection(instances)))  # noqa: E501
    monkeypatch.setattr(route, 'cput', lambda channel, msg: events.append(('publish', channel, msg)))  # noqa: E501
    monkeypatch.setattr(route, 'purge_creature_keys', lambda **kwargs: events.append(('purge', kwargs)))  # noqa: E501

    app = Flask(__name__)
    app.add_url_rule(
        '/remove/<string:instanceid>/<string:creatureid>',
        methods=['POST'],
        view_func=route.remove,
        )
    client = app.test_client()

    def add(_id, instance=INSTANCE_ID, account=None, delete_error=None):
        creatures[_id] = _document(events, creatures, _id, instance, account, delete_error)
        return creatures[_id]

    def post(creatureid=MONSTER_ID, instanceid=INSTANCE_ID, body=None, token=TOKEN):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if body is None:
            body = {
                "reason": 'death',
                "by": str(uuid.uuid4()),
                "at": datetime.datetime.utcnow().isoformat(),
                "requestId": str(uuid.uuid4()),
                }
        return client.post(f'/remove/{instanceid}/{creatureid}', headers=headers, json=body)

    return types.SimpleNamespace(
        add=add, post=post, events=events, creatures=creatures, instances=instances,
        )


#
# The route
#
def test_remove_monster_is_removed(world):
    world.add(MONSTER_ID)

    response = world.post()

    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'removed'}
    assert world.events == [
        ('publish', PS_AI_CREATURE, {
            "action": 'kill',
            "instance": json.dumps({"_id": str(INSTANCE_ID)}),
            "creature": json.dumps({"_id": str(MONSTER_ID), "name": 'Monster'}),
            }),
        ('purge', {"creatureuuid": MONSTER_ID, "instanceuuid": INSTANCE_ID}),
        ('delete', MONSTER_ID),
        ]
    assert MONSTER_ID not in world.creatures


def test_remove_retry_after_removed_is_gone(world):
    world.add(MONSTER_ID)
    assert world.post().json['payload'] == {"result": 'removed'}
    world.events.clear()

    response = world.post()

    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'gone'}
    assert world.events == []


def test_remove_unknown_creature_is_gone(world):
    response = world.post()

    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'gone'}
    assert world.events == []


@pytest.mark.parametrize('instance', [OTHER_INSTANCE_ID, None])
def test_remove_creature_in_another_instance_is_gone(world, instance):
    world.add(MONSTER_ID, instance=instance)

    response = world.post()

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'gone'}
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_unknown_instance_is_404(world):
    world.add(MONSTER_ID, instance=OTHER_INSTANCE_ID)

    response = world.post(instanceid=OTHER_INSTANCE_ID)

    assert response.status_code == 404
    assert response.json['success'] is False
    assert response.json['payload'] is None
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_singouin_is_400_and_touches_nothing(world):
    world.add(SINGOUIN_ID, account=uuid.uuid4())

    response = world.post(creatureid=SINGOUIN_ID)

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []
    assert SINGOUIN_ID in world.creatures


@pytest.mark.parametrize('instanceid, creatureid', [
    ('not-a-uuid', MONSTER_ID),
    (INSTANCE_ID, 'not-a-uuid'),
    ])
def test_remove_malformed_id_is_400(world, instanceid, creatureid):
    world.add(MONSTER_ID)

    response = world.post(creatureid=creatureid, instanceid=instanceid)

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []


@pytest.mark.parametrize('body', [
    [],
    {"reason": 'death', "at": '2026-10-10T00:00:00'},  # requestId missing
    {"reason": 'death', "at": 'yesterday', "requestId": str(uuid.uuid4())},
    ])
def test_remove_invalid_body_is_400(world, body):
    world.add(MONSTER_ID)

    response = world.post(body=body)

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_delete_failure_is_500(world):
    world.add(MONSTER_ID, delete_error=RuntimeError('mongo down'))

    response = world.post()

    assert response.status_code == 500
    assert response.json['success'] is False
    assert response.json['payload'] is None


def test_remove_without_token_is_401(world):
    world.add(MONSTER_ID)

    response = world.post(token=None)

    assert response.status_code == 401
    assert world.events == []
    assert MONSTER_ID in world.creatures


#
# Instance close (utils/instance.py): the kill reaches the AI on its env channel
#
def test_instance_close_publishes_kill_on_env_channel(modules, monkeypatch):
    utils_instance = modules.utils_instance
    events = []

    monster = types.SimpleNamespace(
        id=MONSTER_ID,
        to_json=lambda: json.dumps({"_id": str(MONSTER_ID)}),
        delete=lambda: events.append(('delete', MONSTER_ID)),
        )
    # leave_instance() filters twice: the players (count 1, the leaver is the
    # last one), then the monsters to kill
    results = iter([
        types.SimpleNamespace(count=lambda: 1),
        [monster],
        ])
    monkeypatch.setattr(utils_instance, 'CreatureDocument', types.SimpleNamespace(
        objects=types.SimpleNamespace(filter=lambda query: next(results))))
    monkeypatch.setattr(utils_instance, 'r', types.SimpleNamespace(
        publish=lambda channel, data: events.append(('publish', channel, json.loads(data)))))
    monkeypatch.setattr(utils_instance, 'purge_creature_keys', lambda **kwargs: events.append(('purge', kwargs)))  # noqa: E501
    monkeypatch.setattr(utils_instance, 'purge_instance_keys', lambda **kwargs: events.append(('purge_instance', kwargs)))  # noqa: E501

    leaver = types.SimpleNamespace(id=SINGOUIN_ID, save=lambda: None)
    instance = types.SimpleNamespace(
        id=INSTANCE_ID,
        to_json=lambda: json.dumps({"_id": str(INSTANCE_ID)}),
        delete=lambda: events.append(('delete', INSTANCE_ID)),
        )

    assert utils_instance.leave_instance(leaver, instance) == 'closed'

    assert events == [
        ('purge', {"creatureuuid": SINGOUIN_ID, "instanceuuid": INSTANCE_ID}),
        ('publish', PS_AI_CREATURE, {
            "action": 'kill',
            "instance": json.dumps({"_id": str(INSTANCE_ID)}),
            "creature": json.dumps({"_id": str(MONSTER_ID)}),
            }),
        ('purge', {"creatureuuid": MONSTER_ID, "instanceuuid": INSTANCE_ID}),
        ('delete', MONSTER_ID),
        ('delete', INSTANCE_ID),
        ('purge_instance', {"instanceuuid": INSTANCE_ID}),
        ]


#
# api/variables.py: the channel rule itself, matching ai/variables.py CREATURE_PATH
#
def _load_api_variables(monkeypatch):
    """
    Executes the real api/variables.py under a private name. Its only Mongo
    use is the metas, stubbed empty; nothing is left in sys.modules.
    """
    meta = types.ModuleType('mongo.models.Meta')
    for name in ('MetaArmor', 'MetaRace', 'MetaWeapon'):
        setattr(meta, name, types.SimpleNamespace(objects=lambda: []))
    monkeypatch.setitem(sys.modules, 'mongo.models.Meta', meta)
    monkeypatch.setenv('SEP_SECRET_KEY', 'unit-test-secret')

    path = os.path.join(LOCAL_PATH, 'variables.py')
    spec = importlib.util.spec_from_file_location('_api_variables_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ps_ai_creature_follows_api_env(monkeypatch):
    monkeypatch.setenv('API_ENV', 'DEV')
    assert _load_api_variables(monkeypatch).PS_AI_CREATURE == 'ai-creature-dev'


def test_ps_ai_creature_without_api_env_does_not_crash(monkeypatch):
    monkeypatch.delenv('API_ENV', raising=False)
    assert _load_api_variables(monkeypatch).PS_AI_CREATURE == 'ai-creature-none'


#
# Isolation: runs last in this file, after every use of the fixtures
#
def test_isolation_leaves_no_stub_bound_module():
    for name in ISOLATED:
        parent, _, child = name.rpartition('.')
        current = sys.modules.get(name)
        assert getattr(current, 'CreatureDocument', 'real') is not None
        parent_module = sys.modules.get(parent)
        if parent_module is not None and hasattr(parent_module, child):
            assert getattr(parent_module, child) is current
