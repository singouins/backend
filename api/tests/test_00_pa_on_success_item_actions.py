# -*- coding: utf8 -*-

import importlib.util
import os
import sys
import types
import uuid

import flask_jwt_extended
import pytest
from flask import Flask, g

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# Rulings 2026-10-29 (Lordslair: a refusal is free, PA are only consumed when
# the action is done; chifret: a refusal is not a failure). reload, unload and
# catalyze already consume in their body, after their last refusal: these
# tests pin it. Unit test: no Mongo, no Redis, routes loaded from their files.
ACTION_ROUTES = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'action')
RARITIES = ['Broken', 'Common', 'Uncommon', 'Rare', 'Epic', 'Legendary']
WEAPON_METAID = 1
TICK = 3600
META_NAMES = {
    'weapon': [{
        '_id': WEAPON_METAID, 'pas_reload': 2, 'max_ammo': 6, 'caliber': 'arrow',
        }],
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
def world(monkeypatch):
    """
    Loads reload / unload / catalyze straight from their files. Decorators are
    identities (the views run with g set, as they would), the PA check always
    passes, every side effect appends to `events`.
    """
    events = []
    state = types.SimpleNamespace(ammo=6, shards=10, satchel_error=False)

    def satchel_update(**kwargs):
        if state.satchel_error:
            raise ConnectionError('Mongo down')
        events.append(('satchel',))

    def satchel_get():
        return types.SimpleNamespace(
            ammo=types.SimpleNamespace(arrow=state.ammo),
            shard=types.SimpleNamespace(**{r.lower(): state.shards for r in RARITIES}),
            update=satchel_update,
            reload=lambda: None,
            to_mongo=lambda: {},
            )

    satchels = types.SimpleNamespace(
        filter=lambda **kwargs: types.SimpleNamespace(get=satchel_get, update=satchel_update),
        )
    _module(
        'mongo.models.Satchel', monkeypatch,
        SatchelDocument=types.SimpleNamespace(
            objects=lambda _id=None: satchels if _id is None else types.SimpleNamespace(
                get=satchel_get,
                ),
            ),
        )
    _module(
        'utils.decorators', monkeypatch,
        check_creature_exists=_identity,
        check_item_exists=_identity,
        check_user_exists=_identity,
        check_creature_owned=_identity,
        )
    _module(
        'routes._decorators', monkeypatch,
        exists=types.SimpleNamespace(
            creature=_identity, item=_identity, pa=lambda red=0, blue=0, consume=False: _identity,
            ),
        belongs=types.SimpleNamespace(
            creature_out_of_instance=_identity, item_to_creature=_identity,
            ),
        )
    _module(
        'utils.pa', monkeypatch,
        instance_tick=lambda creature: TICK,
        pa_shortfall_colour=lambda *args: None,
        )
    _module(
        'utils.redis', monkeypatch,
        consume_pa=lambda creatureuuid, redpa=0, bluepa=0, *, tick: events.append(
            ('pa', creatureuuid, redpa, bluepa, tick)),
        get_pa=lambda **kwargs: {'red': {'pa': 16}, 'blue': {'pa': 8}},
        )
    _module('variables', monkeypatch, metaNames=META_NAMES)
    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    routes = {
        'reload': _load('test_pa_on_success_reload', os.path.join(ACTION_ROUTES, 'reload.py')),
        'unload': _load('test_pa_on_success_unload', os.path.join(ACTION_ROUTES, 'unload.py')),
        'catalyze': _load(
            'test_pa_on_success_catalyze', os.path.join(ACTION_ROUTES, 'item', 'catalyze.py'),
            ),
        }
    app = Flask(__name__)
    creature_id = uuid.uuid4()

    def call(name, ammo=0, rarity='Common'):
        item = types.SimpleNamespace(
            id=uuid.uuid4(),
            metaid=WEAPON_METAID,
            metatype='weapon',
            ammo=ammo,
            rarity=rarity,
            save=lambda: events.append(('item',)),
            update=lambda **kwargs: events.append(('item',)),
            reload=lambda: None,
            to_mongo=lambda: {},
            )
        with app.test_request_context():
            g.h = f'[Creature.id:{creature_id}]'
            g.Creature = types.SimpleNamespace(id=creature_id, instance=uuid.uuid4())
            g.Item = item
            view = getattr(routes[name], name)
            response, code = view(creatureuuid=creature_id, itemuuid=item.id)
            return code, response.get_json()

    return types.SimpleNamespace(call=call, creature_id=creature_id, events=events, state=state)


def _assert_refused_free(world, code, body):
    assert code == 200
    assert body['success'] is False
    assert [event for event in world.events if event[0] == 'pa'] == []


#
# reload: refused for lack of ammo after the PA check
#
def test_reload_without_enough_ammo_is_free(world):
    world.state.ammo = 5

    code, body = world.call('reload', ammo=0)

    _assert_refused_free(world, code, body)
    assert 'Not enough Ammo' in body['msg']


def test_reload_pays_once_when_done(world):
    code, body = world.call('reload', ammo=0)

    assert body['success'] is True
    assert world.events == [('item',), ('satchel',), ('pa', world.creature_id, 2, 0, TICK)]


#
# unload: no refusal after the PA check, a failed write is free
#
def test_unload_failed_write_is_free(world):
    world.state.satchel_error = True

    code, body = world.call('unload', ammo=3)

    _assert_refused_free(world, code, body)
    assert 'Unload Query KO' in body['msg']


def test_unload_pays_once_when_done(world):
    code, body = world.call('unload', ammo=3)

    assert body['success'] is True
    assert world.events == [('satchel',), ('item',), ('pa', world.creature_id, 2, 0, TICK)]


#
# catalyze: both refusals come after the PA check
#
def test_catalyze_legendary_is_free(world):
    code, body = world.call('catalyze', rarity='Legendary')

    _assert_refused_free(world, code, body)
    assert 'highest rarity' in body['msg']


def test_catalyze_without_enough_shards_is_free(world):
    world.state.shards = 9

    code, body = world.call('catalyze')

    _assert_refused_free(world, code, body)
    assert 'Not enough shard' in body['msg']


def test_catalyze_pays_once_when_done(world):
    code, body = world.call('catalyze')

    assert body['success'] is True
    assert world.events == [('item',), ('satchel',), ('pa', world.creature_id, 0, 2, TICK)]
