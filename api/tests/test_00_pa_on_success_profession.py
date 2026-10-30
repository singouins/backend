# -*- coding: utf8 -*-

import functools
import importlib.util
import os
import sys
import types
import uuid

import flask_jwt_extended
import pytest
from flask import Flask, g, jsonify

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# Rulings 2026-10-29 (Lordslair: "un refus doit être gratuit [...] Les PA ne
# devraient être consommés que si l'action est réalisée"; chifret: "Être
# refusé est différent de rater. Rater, c'est validé."): out of combat, a
# refusal (not found, not owned, missing resources) costs no PA, a validated
# action costs its PA exactly once, whatever its roll yields.
# Unit test: no Mongo, no Redis, the routes are loaded from their files.
PROFESSION_ROUTES = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'action', 'profession')
TICK = 3600
LOCK_TOKEN = 'lock-token'
# Distinct scores, to tell which one the gathering yield reads
GATHERING = 7
SKINNING = 3
SLOTS = (
    'feet', 'hands', 'head', 'holster', 'lefthand', 'legs', 'righthand', 'shoulders', 'torso',
    )


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


def _refusal(msg):
    return jsonify({"success": False, "msg": msg, "payload": None}), 200


class _QuerySet(list):
    """
    A Mongo queryset: truthy when it holds a document, get() returns it,
    delete() returns how many documents it removed (on_delete decides).
    """
    def __init__(self, documents, on_delete=None):
        super().__init__(documents)
        self.on_delete = on_delete

    def get(self):
        return self[0]

    def delete(self):
        return self.on_delete()


@pytest.fixture
def world(monkeypatch):
    """
    Loads gathering / recycling / tanning / tracking straight from their files
    (the routes.mypc package pulls every route at import). Models, tools and
    Redis are stubbed, every side effect appends to `events`.

    exists.pa is stubbed as the real one behaves: it records its arguments in
    `pa_checks` and, with consume=True only, consumes before the view runs.
    exists.item / belongs.item_to_creature refuse when named in `refuse`.
    """
    events = []
    pa_checks = {}
    refuse = set()
    state = types.SimpleNamespace(
        resource=None, skin=10, redis_error=False, claim_lost=False, scaled=[],
        # Recycling: the Item lock, the Creature as read again from the DB
        # (None: the same as g.Creature), and whether the Item is still there
        item_lock_free=True, locks=[], db_creature=None, item_gone=False,
        )

    def pa(red=0, blue=0, consume=False):
        def decorator(func):
            pa_checks[func.__name__] = {'red': red, 'blue': blue, 'consume': consume}

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if consume is True:
                    events.append(('pa', g.Creature.id, red, blue, TICK))
                return func(*args, **kwargs)
            return wrapper
        return decorator

    def refusing(name):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if name in refuse:
                    return _refusal(f'{name} refused')
                return func(*args, **kwargs)
            return wrapper
        return decorator

    _module(
        'routes._decorators', monkeypatch,
        exists=types.SimpleNamespace(creature=_identity, pa=pa, item=refusing('item')),
        belongs=types.SimpleNamespace(
            creature_in_instance=_identity,
            creature_out_of_instance=_identity,
            item_to_creature=refusing('item_to_creature'),
            ),
        )

    satchel = types.SimpleNamespace(
        update=lambda **kwargs: events.append(('satchel',)),
        reload=lambda: None,
        to_mongo=lambda: {},
        )

    def satchel_get():
        satchel.resource = types.SimpleNamespace(skin=state.skin)
        return satchel

    _module(
        'mongo.models.Highscore', monkeypatch,
        HighscoreDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                update=lambda **kwargs: events.append(('highscore',)),
                update_one=lambda **kwargs: events.append(('highscore',)),
                ),
            ),
        )
    _module(
        'mongo.models.Profession', monkeypatch,
        ProfessionDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                get=lambda: types.SimpleNamespace(gathering=GATHERING, recycling=0, skinning=SKINNING),
                ),
            ),
        )

    def resource_delete():
        # The atomic claim: a concurrent gatherer may have deleted it first
        if state.claim_lost or state.resource is None:
            return 0
        state.resource = None
        events.append(('resource_claim',))
        return 1

    _module(
        'mongo.models.Resource', monkeypatch,
        ResourceDocument=types.SimpleNamespace(
            objects=lambda _id=None: _QuerySet(
                [state.resource] if state.resource else [], on_delete=resource_delete,
                ),
            ),
        )
    _module(
        'mongo.models.Creature', monkeypatch,
        CreatureDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                get=lambda: state.db_creature or creature,
                ),
            ),
        CreatureSlots=types.SimpleNamespace(_fields={name: None for name in SLOTS}),
        )

    def lock_item(itemuuid):
        state.locks.append(('lock', itemuuid))
        return LOCK_TOKEN if state.item_lock_free else None

    def delete_locked_item(itemuuid, token):
        # Gone, or its lock expired and was taken over: nothing deleted
        if state.item_gone or token != LOCK_TOKEN:
            return False
        events.append(('item_delete',))
        return True

    _module(
        'utils.item_lock', monkeypatch,
        lock_item=lock_item,
        unlock_item=lambda itemuuid, token: state.locks.append(('unlock', itemuuid, token)),
        delete_locked_item=delete_locked_item,
        )
    _module(
        'mongo.models.Satchel', monkeypatch,
        SatchelDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                get=satchel_get,
                update_one=lambda **kwargs: events.append(('satchel',)),
                ),
            ),
        )
    _module(
        'routes.mypc.action.profession._tools', monkeypatch,
        probabilistic_binary=lambda stat: 0,
        profession_gain=lambda *args: events.append(('profession',)),
        profession_scaled=lambda score: state.scaled.append(score) or 0,
        )
    _module('utils.pa', monkeypatch, instance_tick=lambda creature: TICK)

    def hset(key, mapping):
        if state.redis_error:
            raise ConnectionError('Redis down')
        events.append(('effect', mapping['name']))

    _module(
        'utils.redis', monkeypatch,
        r=types.SimpleNamespace(hset=hset, expire=lambda key, ttl: None),
        consume_pa=lambda creatureuuid, redpa=0, bluepa=0, *, tick: events.append(
            ('pa', creatureuuid, redpa, bluepa, tick)),
        get_pa=lambda **kwargs: {'pa': 'stub'},
        )
    _module(
        'variables', monkeypatch,
        env_vars={'API_ENV': 'TEST'},
        )
    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    routes = {
        name: _load(f'test_pa_on_success_{name}', os.path.join(PROFESSION_ROUTES, f'{name}.py'))
        for name in ('gathering', 'recycling', 'tanning', 'tracking')
        }
    app = Flask(__name__)
    creature = types.SimpleNamespace(
        id=uuid.uuid4(),
        instance=uuid.uuid4(),
        x=1,
        y=1,
        slots=None,
        stats=types.SimpleNamespace(total=types.SimpleNamespace(m=50, b=50)),
        )

    def call(name, item=None, **kwargs):
        with app.test_request_context():
            g.h = f'[Creature.id:{creature.id}]'
            g.Creature = creature
            g.Item = item
            view = getattr(routes[name], name)
            response, code = view(creatureuuid=creature.id, **kwargs)
            return code, response.get_json()

    return types.SimpleNamespace(
        call=call, creature=creature, events=events, pa_checks=pa_checks,
        refuse=refuse, state=state,
        )


def _resource(world, rarity, x=1, y=1, instance=None):
    """ A Resource in the Creature's instance, by default on its cell. """
    world.state.resource = types.SimpleNamespace(
        id=uuid.uuid4(),
        instance=world.creature.instance if instance is None else instance,
        rarity=rarity,
        x=x,
        y=y,
        )
    return world.state.resource


def _item(world, rarity):
    return types.SimpleNamespace(id=uuid.uuid4(), rarity=rarity)


def _pa_events(world):
    return [event for event in world.events if event[0] == 'pa']


def _assert_refused_free(world, code, body):
    assert code == 200
    assert body['success'] is False
    # A refusal is free: no PA consumed, nothing done
    assert world.events == []


@pytest.mark.parametrize('route, red, blue', [
    ('gathering', 0, 4),
    ('recycling', 0, 2),
    ('tanning', 0, 2),
    ('tracking', 0, 2),
    ])
def test_decorator_checks_pa_without_consuming(world, route, red, blue):
    assert world.pa_checks[route] == {'red': red, 'blue': blue, 'consume': False}


#
# gathering
#
def test_gathering_resource_not_found_is_free(world):
    code, body = world.call('gathering', resourceuuid=uuid.uuid4())

    _assert_refused_free(world, code, body)
    assert 'NotFound' in body['msg']


def test_gathering_pays_once_before_any_credit(world):
    _resource(world, 'Common')

    code, body = world.call('gathering', resourceuuid=uuid.uuid4())

    assert code == 200
    assert body['success'] is True
    # The Resource is claimed (deleted) first, then paid for, then credited
    assert world.events == [
        ('resource_claim',),
        ('pa', world.creature.id, 0, 4, TICK),
        ('profession',),
        ('highscore',),
        ('satchel',),
        ]


def test_gathering_zero_yield_still_pays_once(world):
    # A validated gathering that yields nothing failed, it was not refused
    _resource(world, 'Legendary')

    code, body = world.call('gathering', resourceuuid=uuid.uuid4())

    assert body['payload']['resource'][0]['count'] == 0
    assert _pa_events(world) == [('pa', world.creature.id, 0, 4, TICK)]


def test_gathering_yield_reads_the_gathering_score(world):
    # It read Profession.skinning
    _resource(world, 'Common')

    world.call('gathering', resourceuuid=uuid.uuid4())

    assert world.state.scaled == [GATHERING]


def test_gathering_in_another_instance_is_free(world):
    resource = _resource(world, 'Common', instance=uuid.uuid4())

    code, body = world.call('gathering', resourceuuid=resource.id)

    _assert_refused_free(world, code, body)
    assert 'not in this instance' in body['msg']
    assert world.state.resource is resource


# Lordslair 2026-10-29: "prenons les mêmes règles que pour dépeçage pour la
# distance": the Creature's cell or an adjacent one (Creature at (1, 1))
@pytest.mark.parametrize('x, y', [(1, 1), (0, 0), (2, 2), (0, 2), (2, 1), (1, 0)])
def test_gathering_within_one_cell_is_done(world, x, y):
    _resource(world, 'Common', x=x, y=y)

    code, body = world.call('gathering', resourceuuid=uuid.uuid4())

    assert body['success'] is True
    assert world.state.resource is None


@pytest.mark.parametrize('x, y', [(3, 1), (1, 3), (-1, 1), (1, -1), (3, 3), (-1, -1)])
def test_gathering_two_cells_away_is_free(world, x, y):
    resource = _resource(world, 'Common', x=x, y=y)

    code, body = world.call('gathering', resourceuuid=resource.id)

    _assert_refused_free(world, code, body)
    assert 'not in range' in body['msg']
    assert world.state.resource is resource


@pytest.mark.parametrize('attribute', ['x', 'y'])
def test_gathering_without_a_position_is_free(world, attribute):
    # x/y default to None on a Creature: no range, and no TypeError (500)
    setattr(world.creature, attribute, None)
    _resource(world, 'Common')

    code, body = world.call('gathering', resourceuuid=uuid.uuid4())

    _assert_refused_free(world, code, body)
    assert 'not in range' in body['msg']


def test_gathering_lost_claim_is_free(world):
    # Two gatherers on one Resource: the one whose delete removed nothing is
    # refused, unpaid and uncredited
    _resource(world, 'Common')
    world.state.claim_lost = True

    code, body = world.call('gathering', resourceuuid=uuid.uuid4())

    _assert_refused_free(world, code, body)
    assert 'already gathered' in body['msg']


#
# recycling
#
@pytest.mark.parametrize('refusal', ['item', 'item_to_creature'])
def test_recycling_item_refusal_is_free(world, refusal):
    world.refuse.add(refusal)

    code, body = world.call('recycling', itemuuid=uuid.uuid4())

    _assert_refused_free(world, code, body)


def test_recycling_pays_once_before_any_credit(world):
    item = _item(world, 'Common')

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    assert code == 200
    assert body['success'] is True
    # The Item is deleted first (the claim), then paid for, then credited
    assert world.events == [
        ('item_delete',),
        ('pa', world.creature.id, 0, 2, TICK),
        ('highscore',),
        ('satchel',),
        ('profession',),
        ]
    # Locked first; a deleted Item has no lock left to release
    assert world.state.locks == [('lock', item.id)]


@pytest.mark.parametrize('slotname', SLOTS)
def test_recycling_equipped_item_is_free(world, slotname):
    # Recycling deleted it and left its slot pointing at nothing
    item = _item(world, 'Common')
    world.creature.slots = types.SimpleNamespace(**{name: None for name in SLOTS})
    setattr(world.creature.slots, slotname, types.SimpleNamespace(id=item.id))

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    _assert_refused_free(world, code, body)
    assert 'is equipped' in body['msg']
    # The lock taken to read the slots is released: the Item stays usable
    assert world.state.locks == [('lock', item.id), ('unlock', item.id, LOCK_TOKEN)]


def test_recycling_reads_the_slots_again_once_locked(world):
    # Lordslair 2026-10-29: an equip that ended after this request loaded the
    # Creature must not let an equipped Item be recycled
    item = _item(world, 'Common')
    world.state.db_creature = types.SimpleNamespace(
        slots=types.SimpleNamespace(**{name: None for name in SLOTS}),
        )
    world.state.db_creature.slots.righthand = types.SimpleNamespace(id=item.id)

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    _assert_refused_free(world, code, body)
    assert 'is equipped' in body['msg']


def test_recycling_of_a_locked_item_is_free(world):
    # Lordslair 2026-10-29: another recycling or an equip holds the Item
    item = _item(world, 'Common')
    world.state.item_lock_free = False

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    _assert_refused_free(world, code, body)
    assert 'busy or already recycled' in body['msg']
    assert world.state.locks == [('lock', item.id)]


def test_recycling_of_an_item_already_deleted_is_free(world):
    # Lordslair 2026-10-29: two recyclings of one Item credit the shards once.
    # The loser's delete removes nothing: refused, unpaid, uncredited
    item = _item(world, 'Common')
    world.state.item_gone = True

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    _assert_refused_free(world, code, body)
    assert 'already recycled' in body['msg']


def test_recycling_item_equipped_elsewhere_is_done(world):
    # Another Item in the slots, empty slots (None, or id None): not this one
    item = _item(world, 'Common')
    world.creature.slots = types.SimpleNamespace(**{name: None for name in SLOTS})
    world.creature.slots.righthand = types.SimpleNamespace(id=uuid.uuid4())
    world.creature.slots.head = types.SimpleNamespace(id=None)

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    assert body['success'] is True
    assert ('item_delete',) in world.events


def test_recycling_zero_shards_still_pays_once(world):
    item = _item(world, 'Legendary')

    code, body = world.call('recycling', item=item, itemuuid=item.id)

    assert body['payload']['resource'][0]['count'] == 0
    assert _pa_events(world) == [('pa', world.creature.id, 0, 2, TICK)]


#
# tanning
#
def test_tanning_without_enough_skin_is_free(world):
    world.state.skin = 9

    code, body = world.call('tanning')

    _assert_refused_free(world, code, body)
    assert 'Not enough resource.skin' in body['msg']


def test_tanning_pays_once_before_any_credit(world):
    code, body = world.call('tanning')

    assert code == 200
    assert body['success'] is True
    assert world.events == [
        ('pa', world.creature.id, 0, 2, TICK),
        ('highscore',),
        ('satchel',),
        ('profession',),
        ]


#
# tracking
#
def test_tracking_redis_error_is_free(world):
    world.state.redis_error = True

    code, body = world.call('tracking')

    _assert_refused_free(world, code, body)
    assert 'Redis Query KO' in body['msg']


def test_tracking_pays_once_after_the_effect(world):
    code, body = world.call('tracking')

    assert code == 200
    assert body['success'] is True
    assert world.events == [
        ('effect', 'Tracking'),
        ('pa', world.creature.id, 0, 2, TICK),
        ('highscore',),
        ]
