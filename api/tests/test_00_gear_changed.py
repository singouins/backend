# -*- coding: utf8 -*-

import datetime
import importlib.util
import os
import sys
import types
import uuid

from unittest.mock import MagicMock

import flask_jwt_extended
import pytest
import requests
from flask import Flask, g
from loguru import logger

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

from utils import resolver  # noqa: E402

# Design ruling (2026-10-28, option A): after a successful equip, unequip or
# offset, the API notifies the resolver (POST .../gear-changed) so it
# recomputes the creature gear-derived state. Pure unit test: no Mongo, no
# Redis, no network (requests.post is mocked).
REPO_PATH = os.path.join(LOCAL_PATH, os.pardir)
CREATURE_MODEL = os.path.join(REPO_PATH, 'mongo', 'models', 'Creature.py')
INVENTORY_ROUTES = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'inventory')

RESOLVER_URL = 'http://resolver-test:3000'
TOKEN = 'test-resolver-token'
CREATURE_ID = uuid.uuid4()
INSTANCE_ID = uuid.uuid4()
ITEM_ID = uuid.uuid4()
LOCK_TOKEN = 'lock-token'
WEAPON_METAID = 1
NO_MINS = {'min_m': 0, 'min_r': 0, 'min_g': 0, 'min_v': 0, 'min_p': 0, 'min_b': 0}
META_INDEXED = {
    'armor': {},
    'weapon': {
        WEAPON_METAID: {'_id': WEAPON_METAID, 'size': '1x2', 'onehanded': True, **NO_MINS},
        },
    }


def _identity(func):
    return func


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def logs():
    """ Collects loguru messages (caplog does not see loguru). """
    records = []
    sink_id = logger.add(lambda message: records.append(message.record), level='TRACE')
    yield records
    logger.remove(sink_id)


@pytest.fixture
def variables(monkeypatch):
    """ An explicit variables stub, read lazily by notify_gear_changed. """
    stub = types.ModuleType('variables')
    stub.RESOLVER_URL = RESOLVER_URL
    stub.RESOLVER_INTERNAL_TOKEN = TOKEN
    stub.metaIndexed = META_INDEXED
    # equip / unequip publish the ws broadcast on env_vars['PS_BROADCAST']
    stub.env_vars = {'PS_BROADCAST': 'ws-broadcast-test'}
    monkeypatch.setitem(sys.modules, 'variables', stub)
    return stub


@pytest.fixture
def post(monkeypatch):
    mock = MagicMock(return_value=MagicMock(status_code=200))
    monkeypatch.setattr(resolver.requests, 'post', mock)
    return mock


def _creature(instance=INSTANCE_ID):
    return types.SimpleNamespace(id=CREATURE_ID, instance=instance)


def _warnings(logs):
    return [record['message'] for record in logs if record['level'].name == 'WARNING']


#
# notify_gear_changed
#
def test_notify_not_in_an_instance_makes_no_call(variables, post):
    resolver.notify_gear_changed(_creature(instance=None), 'equip')

    post.assert_not_called()


@pytest.mark.parametrize('token', [None, ''])
def test_notify_token_unset_makes_no_call(variables, post, token):
    variables.RESOLVER_INTERNAL_TOKEN = token

    resolver.notify_gear_changed(_creature(), 'equip')

    post.assert_not_called()


@pytest.mark.parametrize('reason', ['equip', 'unequip', 'offset'])
def test_notify_posts_url_bearer_and_body(variables, post, reason):
    before = datetime.datetime.now(datetime.timezone.utc)

    resolver.notify_gear_changed(_creature(), reason)

    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == (f'{RESOLVER_URL}/internal/instance/{INSTANCE_ID}'
                       f'/creature/{CREATURE_ID}/gear-changed')
    assert kwargs['headers'] == {"Authorization": f"Bearer {TOKEN}"}
    assert kwargs['timeout'] == (1, 2)
    body = kwargs['json']
    assert set(body) == {'reason', 'by', 'at', 'requestId'}
    assert body['reason'] == reason
    assert body['by'] == str(CREATURE_ID)
    at = datetime.datetime.fromisoformat(body['at'])
    assert at.utcoffset() == datetime.timedelta(0)
    assert at >= before
    assert uuid.UUID(body['requestId']).version == 4


def test_notify_ok_logs_debug_only(variables, post, logs):
    resolver.notify_gear_changed(_creature(), 'equip')

    assert _warnings(logs) == []
    assert any('resolver call OK' in record['message'] for record in logs)


@pytest.mark.parametrize('error', [
    requests.exceptions.Timeout('read timed out'),
    requests.exceptions.ConnectionError('connection refused'),
    RuntimeError('anything else'),
    ])
def test_notify_swallows_exceptions_and_warns(variables, post, logs, error):
    post.side_effect = error

    resolver.notify_gear_changed(_creature(), 'unequip')

    warnings = _warnings(logs)
    assert len(warnings) == 1
    assert str(CREATURE_ID) in warnings[0]
    assert 'unequip' in warnings[0]
    assert type(error).__name__ in warnings[0]


@pytest.mark.parametrize('status', [401, 404, 500, 503])
def test_notify_non_200_is_swallowed_and_warns_with_status(variables, post, logs, status):
    post.return_value = MagicMock(status_code=status)

    resolver.notify_gear_changed(_creature(), 'offset')

    warnings = _warnings(logs)
    assert len(warnings) == 1
    assert f'status:{status}' in warnings[0]
    assert str(CREATURE_ID) in warnings[0]
    assert 'offset' in warnings[0]


def test_notify_settings_missing_is_swallowed_and_warns(monkeypatch, post, logs):
    """ A variables module without the resolver settings must not break the route. """
    monkeypatch.setitem(sys.modules, 'variables', types.ModuleType('variables'))

    resolver.notify_gear_changed(_creature(), 'equip')

    post.assert_not_called()
    warnings = _warnings(logs)
    assert len(warnings) == 1
    assert str(CREATURE_ID) in warnings[0]


def test_notify_never_logs_the_token(variables, post, logs):
    post.side_effect = requests.exceptions.ConnectionError('connection refused')
    resolver.notify_gear_changed(_creature(), 'equip')
    post.side_effect = None
    post.return_value = MagicMock(status_code=500)
    resolver.notify_gear_changed(_creature(), 'equip')
    post.return_value = MagicMock(status_code=200)
    resolver.notify_gear_changed(_creature(), 'equip')

    assert logs
    assert all(TOKEN not in record['message'] for record in logs)


#
# Routes: one notify on the success path, none on a refusal
#
@pytest.fixture
def routes(monkeypatch, variables):
    """
    Loads equip.py, unequip.py and offset.py straight from their files, as
    test_00_equip_params.py does: real Creature model, stubbed decorators,
    utils.redis and Item model. The views run with g already set.
    """
    creature_model = _load('mongo.models.Creature', CREATURE_MODEL)
    monkeypatch.setitem(sys.modules, 'mongo.models.Creature', creature_model)

    item_model = types.ModuleType('mongo.models.Item')
    item_model.ItemDocument = types.SimpleNamespace(objects=lambda **kwargs: [])
    monkeypatch.setitem(sys.modules, 'mongo.models.Item', item_model)

    decorators = types.ModuleType('utils.decorators')
    decorators.check_creature_exists = _identity
    decorators.check_item_exists = _identity
    decorators.check_creature_pa = lambda red, blue: _identity
    monkeypatch.setitem(sys.modules, 'utils.decorators', decorators)

    redis_stub = types.ModuleType('utils.redis')
    redis_stub.r = None
    redis_stub.get_pa = None
    redis_stub.consume_pa = None
    monkeypatch.setitem(sys.modules, 'utils.redis', redis_stub)

    # Always granted, recorded by the world fixture (the lock itself: test_00_item_lock.py)
    item_lock = types.ModuleType('utils.item_lock')
    item_lock.lock_item = lambda itemuuid: 'token'
    item_lock.unlock_item = lambda itemuuid, token: None
    monkeypatch.setitem(sys.modules, 'utils.item_lock', item_lock)

    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    equip = _load('test_gear_equip_route', os.path.join(INVENTORY_ROUTES, 'equip.py'))
    unequip = _load('test_gear_unequip_route', os.path.join(INVENTORY_ROUTES, 'unequip.py'))
    offset = _load('test_gear_offset_route', os.path.join(INVENTORY_ROUTES, 'offset.py'))
    return types.SimpleNamespace(equip=equip, unequip=unequip, offset=offset, model=creature_model)


@pytest.fixture
def world(routes, monkeypatch):
    """
    Calls the views in a request context. notify_gear_changed is replaced at
    the route module level; every call lands in `events` after the saves.
    """
    events = []
    creature = types.SimpleNamespace(
        id=CREATURE_ID,
        instance=INSTANCE_ID,
        slots=routes.model.CreatureSlots(),
        stats=types.SimpleNamespace(
            total=types.SimpleNamespace(m=50, r=50, g=50, v=50, p=50, b=50),
            ),
        updated=None,
        save=lambda: events.append('save'),
        to_mongo=lambda: {"_id": str(CREATURE_ID)},
        )
    item = types.SimpleNamespace(
        id=ITEM_ID,
        metaid=WEAPON_METAID,
        metatype='weapon',
        offsetx=None,
        offsety=None,
        updated=None,
        save=lambda: events.append('item_save'),
        )

    for module in (routes.equip, routes.unequip, routes.offset):
        monkeypatch.setattr(
            module,
            'notify_gear_changed',
            lambda creature, reason: events.append(('notify', creature, reason)),
            )
    for module in (routes.equip, routes.unequip):
        # No PA pool to read or consume: the PA logic is not under test here
        monkeypatch.setattr(module, 'instance_tick', lambda creature: None)
        monkeypatch.setattr(module, 'get_pa', lambda **kwargs: None)
        monkeypatch.setattr(module, 'r', types.SimpleNamespace(
            publish=lambda channel, data: events.append(('publish', channel)),
            ))
    monkeypatch.setattr(routes.equip, 'consume_pa', lambda **kwargs: events.append('consume_pa'))
    lock = types.SimpleNamespace(free=True)

    def lock_item(itemuuid):
        events.append(('lock', itemuuid))
        return LOCK_TOKEN if lock.free else None

    monkeypatch.setattr(routes.equip, 'lock_item', lock_item, raising=False)
    monkeypatch.setattr(
        routes.equip, 'unlock_item', lambda itemuuid, token: events.append(('unlock', itemuuid, token)),
        raising=False,
        )

    app = Flask(__name__)

    def call(view, **kwargs):
        with app.test_request_context():
            g.h = f'[Item.id:{ITEM_ID}]'
            g.Creature = creature
            g.Item = item
            response, code = view(creatureuuid=CREATURE_ID, itemuuid=ITEM_ID, **kwargs)
            return code, response.get_json()

    return types.SimpleNamespace(
        equip=lambda type, slotname: call(routes.equip.equip, type=type, slotname=slotname),
        unequip=lambda type, slotname: call(routes.unequip.unequip, type=type, slotname=slotname),
        offset=lambda x, y: call(routes.offset.offset, offsetx=x, offsety=y),
        creature=creature,
        item=item,
        events=events,
        lock=lock,
        )


def _notifies(events):
    return [event for event in events if event[0] == 'notify']


def test_equip_success_notifies_after_save(world):
    code, body = world.equip('weapon', 'righthand')

    assert code == 200
    assert body['success'] is True
    assert _notifies(world.events) == [('notify', world.creature, 'equip')]
    assert world.events.index('save') < world.events.index(_notifies(world.events)[0])


@pytest.mark.parametrize('type, slotname', [
    ('weapon', 'head'),      # weapon in an armour slot: 400
    ('weapon', 'bogus'),     # unknown slot: 400
    ('armor', 'righthand'),  # not the item metatype: 400
    ])
def test_equip_refused_does_not_notify(world, type, slotname):
    code, body = world.equip(type, slotname)

    assert body['success'] is False
    assert _notifies(world.events) == []


def test_equip_holds_the_item_lock_around_the_save(world):
    # Lordslair 2026-10-29: an equip racing a recycling of the same Item must
    # not pass; both routes lock the Item (utils/item_lock.py)
    code, body = world.equip('weapon', 'righthand')

    assert body['success'] is True
    # Released with the token it got: never someone else's lock
    assert world.events[:3] == [('lock', ITEM_ID), 'save', ('unlock', ITEM_ID, LOCK_TOKEN)]
    assert world.events.index(('unlock', ITEM_ID, LOCK_TOKEN)) < world.events.index('consume_pa')


def test_equip_of_a_locked_item_is_free(world):
    # A recycling holds the Item (or deleted it): no slot written, no PA, no notify
    world.lock.free = False

    code, body = world.equip('weapon', 'righthand')

    assert code == 200
    assert body['success'] is False
    assert 'busy or gone' in body['msg']
    assert world.events == [('lock', ITEM_ID)]


def test_equip_releases_the_lock_when_the_save_fails(world):
    def failing_save():
        raise RuntimeError('Mongo down')
    world.creature.save = failing_save

    with pytest.raises(RuntimeError):
        world.equip('weapon', 'righthand')

    assert world.events == [('lock', ITEM_ID), ('unlock', ITEM_ID, LOCK_TOKEN)]


def test_unequip_success_notifies_after_save(world):
    world.equip('weapon', 'righthand')
    world.events.clear()

    code, body = world.unequip('weapon', 'righthand')

    assert code == 200
    assert body['success'] is True
    assert world.events[0] == 'save'
    assert _notifies(world.events) == [('notify', world.creature, 'unequip')]


def test_unequip_refused_unknown_slot_does_not_notify(world):
    code, body = world.unequip('weapon', 'bogus')

    assert code == 400
    assert body['success'] is False
    assert world.events == []


def test_unequip_failed_query_does_not_notify(world):
    """ Nothing in the right hand: the query fails (KO 200), nothing saved. """
    code, body = world.unequip('weapon', 'righthand')

    assert code == 200
    assert body['success'] is False
    assert world.events == []


def test_offset_success_notifies_after_save(world):
    code, body = world.offset(2, 3)

    assert code == 200
    assert body['success'] is True
    assert (world.item.offsetx, world.item.offsety) == (2, 3)
    assert world.events == ['item_save', ('notify', world.creature, 'offset')]


def test_offset_failed_save_does_not_notify(world):
    def failing_save():
        raise RuntimeError('store down')
    world.item.save = failing_save

    code, body = world.offset(2, 3)

    assert code == 200
    assert body['success'] is False
    assert _notifies(world.events) == []


#
# Route + real helper: a resolver failure never breaks the player action
#
def test_equip_succeeds_when_the_resolver_times_out(routes, variables, monkeypatch, logs):
    post = MagicMock(side_effect=requests.exceptions.Timeout('read timed out'))
    monkeypatch.setattr(resolver.requests, 'post', post)
    creature = types.SimpleNamespace(
        id=CREATURE_ID,
        instance=INSTANCE_ID,
        slots=routes.model.CreatureSlots(),
        stats=types.SimpleNamespace(
            total=types.SimpleNamespace(m=50, r=50, g=50, v=50, p=50, b=50),
            ),
        updated=None,
        save=lambda: None,
        to_mongo=lambda: {"_id": str(CREATURE_ID)},
        )
    monkeypatch.setattr(routes.equip, 'instance_tick', lambda creature: None)
    monkeypatch.setattr(routes.equip, 'get_pa', lambda **kwargs: None)
    monkeypatch.setattr(routes.equip, 'consume_pa', lambda **kwargs: None)
    monkeypatch.setattr(
        routes.equip, 'r', types.SimpleNamespace(publish=lambda channel, data: None),
        )

    with Flask(__name__).test_request_context():
        g.h = f'[Item.id:{ITEM_ID}]'
        g.Creature = creature
        g.Item = types.SimpleNamespace(id=ITEM_ID, metaid=WEAPON_METAID, metatype='weapon')
        response, code = routes.equip.equip(
            creatureuuid=CREATURE_ID, type='weapon', slotname='righthand', itemuuid=ITEM_ID,
            )

    assert code == 200
    assert response.get_json()['success'] is True
    post.assert_called_once()
    assert len(_warnings(logs)) == 1
