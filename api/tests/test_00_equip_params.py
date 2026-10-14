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

# The equip / unequip path parameters (type, slotname) used to be trusted:
# an unknown type, a type that is not the item metatype, a missing meta or a
# slotname that is not a Creature slot ended in a 500. They now answer
# 400 / 404 before any PA logic, as does a slot of another item category
# (design ruling 2026-10-14). Pure unit test: no Mongo, no Redis.
REPO_PATH = os.path.join(LOCAL_PATH, os.pardir)
CREATURE_MODEL = os.path.join(REPO_PATH, 'mongo', 'models', 'Creature.py')
INVENTORY_ROUTES = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'inventory')

CREATURE_ID = uuid.uuid4()
ITEM_ID = uuid.uuid4()
WEAPON_METAID = 1
ARMOR_METAID = 2
NO_MINS = {'min_m': 0, 'min_r': 0, 'min_g': 0, 'min_v': 0, 'min_p': 0, 'min_b': 0}
# One armour meta per armors.json 'slot' value (ids 10..16), plus broken ones
ARMOR_SLOT_METAIDS = {
    slot: 10 + index for index, slot in enumerate(
        ['Feet', 'Hands', 'Head', 'Legs', 'Shoulders', 'Torso', 'Shield'],
        )
    }
UNKNOWN_SLOT_METAID = 20
MISSING_SLOT_METAID = 21
# Shields by size (the ARMOR_SLOT_METAIDS one is 2x2), and a 2x3 weapon
SHIELD_2X3_METAID = 22
SHIELD_2X4_METAID = 23
WEAPON_2X3_METAID = 3
META_INDEXED = {
    'armor': {
        ARMOR_METAID: {'_id': ARMOR_METAID, 'size': '2x2', 'slot': 'Head', **NO_MINS},
        **{
            metaid: {'_id': metaid, 'size': '2x2', 'slot': slot, **NO_MINS}
            for slot, metaid in ARMOR_SLOT_METAIDS.items()
            },
        UNKNOWN_SLOT_METAID: {
            '_id': UNKNOWN_SLOT_METAID, 'size': '2x2', 'slot': 'Tail', **NO_MINS,
            },
        MISSING_SLOT_METAID: {'_id': MISSING_SLOT_METAID, 'size': '2x2', **NO_MINS},
        SHIELD_2X3_METAID: {
            '_id': SHIELD_2X3_METAID, 'size': '2x3', 'slot': 'Shield', **NO_MINS,
            },
        SHIELD_2X4_METAID: {
            '_id': SHIELD_2X4_METAID, 'size': '2x4', 'slot': 'Shield', **NO_MINS,
            },
        },
    'weapon': {
        WEAPON_METAID: {
            '_id': WEAPON_METAID, 'size': '1x2', 'onehanded': True,
            'min_m': 0, 'min_r': 0, 'min_g': 0, 'min_v': 0, 'min_p': 0, 'min_b': 0,
            },
        WEAPON_2X3_METAID: {
            '_id': WEAPON_2X3_METAID, 'size': '2x3', 'onehanded': True, **NO_MINS,
            },
        },
    'race': {
        WEAPON_METAID: {'_id': WEAPON_METAID, 'name': 'Singouin'},
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
def modules(monkeypatch):
    """
    Loads equip.py and unequip.py straight from their files (the routes.mypc
    package __init__ pulls every route). The real Creature model is loaded
    from its file (mongoengine does not connect at class definition), so the
    slot names come from CreatureSlots itself. The decorators and utils.redis
    are stubbed: the views run with g already set, as the decorators would.
    """
    creature_model = _load('mongo.models.Creature', CREATURE_MODEL)
    monkeypatch.setitem(sys.modules, 'mongo.models.Creature', creature_model)

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

    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)
    # equip.py reads only metaIndexed from variables: an explicit stub, so the
    # test does not depend on conftest having imported tests/variables.py
    variables = types.ModuleType('variables')
    variables.metaIndexed = META_INDEXED
    monkeypatch.setitem(sys.modules, 'variables', variables)

    equip = _load('test_equip_route', os.path.join(INVENTORY_ROUTES, 'equip.py'))
    unequip = _load('test_unequip_route', os.path.join(INVENTORY_ROUTES, 'unequip.py'))
    return types.SimpleNamespace(equip=equip, unequip=unequip, model=creature_model)


@pytest.fixture
def world(modules, monkeypatch):
    """
    Calls the views in a request context with g.Creature / g.Item set.
    Outside an Instance (instance_tick None), so no PA pool is read; the
    calls that reach the normal path are recorded in `events`.
    """
    events = []
    creature = types.SimpleNamespace(
        id=CREATURE_ID,
        instance=None,
        slots=modules.model.CreatureSlots(),
        stats=types.SimpleNamespace(
            total=types.SimpleNamespace(m=50, r=50, g=50, v=50, p=50, b=50),
            ),
        updated=None,
        save=lambda: events.append('save'),
        to_mongo=lambda: {"_id": str(CREATURE_ID)},
        )

    for module in (modules.equip, modules.unequip):
        monkeypatch.setattr(module, 'instance_tick', lambda creature: None)
        monkeypatch.setattr(module, 'get_pa', lambda **kwargs: None)
        monkeypatch.setattr(module, 'r', types.SimpleNamespace(
            publish=lambda channel, data: events.append(('publish', channel)),
            ))
    monkeypatch.setattr(
        modules.equip, 'consume_pa', lambda **kwargs: events.append(('consume_pa', kwargs)),
        )

    app = Flask(__name__)

    def call(view, type, slotname, metatype='weapon', metaid=WEAPON_METAID):
        with app.test_request_context():
            g.h = f'[Item.id:{ITEM_ID}]'
            g.Creature = creature
            g.Item = types.SimpleNamespace(id=ITEM_ID, metaid=metaid, metatype=metatype)
            response, code = view(
                creatureuuid=CREATURE_ID,
                type=type,
                slotname=slotname,
                itemuuid=ITEM_ID,
                )
            return code, response.get_json()

    def equip(type, slotname, **kwargs):
        return call(modules.equip.equip, type, slotname, **kwargs)

    def unequip(type, slotname, **kwargs):
        return call(modules.unequip.unequip, type, slotname, **kwargs)

    return types.SimpleNamespace(equip=equip, unequip=unequip, creature=creature, events=events)


def _assert_refused(code, body, expected_code):
    assert code == expected_code
    assert body['success'] is False
    assert body['payload'] is None


#
# equip
#
def test_equip_type_consumable_is_400(world):
    """ consumable is not in metaIndexed: used to be a 500 KeyError. """
    code, body = world.equip('consumable', 'righthand', metatype='consumable')

    _assert_refused(code, body, 400)
    assert world.events == []


def test_equip_type_race_is_400(world):
    """ race is in metaIndexed but has no size: used to be a 500 KeyError 'size'. """
    code, body = world.equip('race', 'righthand', metatype='race')

    _assert_refused(code, body, 400)
    assert world.events == []


def test_equip_type_not_the_item_metatype_is_400(world):
    """ An equipable type that is not the item metatype must not read another meta table. """
    code, body = world.equip('armor', 'head', metatype='weapon', metaid=WEAPON_METAID)

    _assert_refused(code, body, 400)
    assert world.events == []


@pytest.mark.parametrize('slotname', ['bogus', 'validate', '_data'])
def test_equip_unknown_slotname_is_400(world, slotname):
    """ Not a CreatureSlots field: setattr() used to accept anything. """
    code, body = world.equip('weapon', slotname)

    _assert_refused(code, body, 400)
    assert slotname in body['msg']
    assert world.events == []


def test_equip_missing_meta_is_404(world):
    """ A metaid absent from the meta table used to be a 500 IndexError. """
    code, body = world.equip('weapon', 'righthand', metaid=999)

    _assert_refused(code, body, 404)
    assert world.events == []


def test_equip_valid_weapon_reaches_the_normal_path(world):
    code, body = world.equip('weapon', 'righthand')

    assert code == 200
    assert body['success'] is True
    assert world.creature.slots.righthand.id == ITEM_ID
    assert world.events[0] == 'save'
    assert world.events[1][0] == 'consume_pa'
    assert world.events[2] == ('publish', 'ws-broadcast')


def test_equip_valid_armor_reaches_the_generic_slot(world):
    code, body = world.equip('armor', 'head', metatype='armor', metaid=ARMOR_METAID)

    assert code == 200
    assert body['success'] is True
    assert world.creature.slots.head.id == ITEM_ID


#
# equip: a slot only accepts its own category (design ruling 2026-10-14)
#
ARMOR_SLOTNAMES = ['feet', 'hands', 'head', 'legs', 'shoulders', 'torso']


@pytest.mark.parametrize('slot', ['Feet', 'Hands', 'Head', 'Legs', 'Shoulders', 'Torso'])
def test_allowed_slots_armor_is_its_own_slot(modules, slot):
    meta = META_INDEXED['armor'][ARMOR_SLOT_METAIDS[slot]]

    assert modules.equip.allowed_slots('armor', meta) == {slot.lower()}


def test_allowed_slots_shield_is_lefthand_only(modules):
    meta = META_INDEXED['armor'][ARMOR_SLOT_METAIDS['Shield']]

    assert modules.equip.allowed_slots('armor', meta) == {'lefthand'}


def test_allowed_slots_weapon_is_hands_and_holster(modules):
    meta = META_INDEXED['weapon'][WEAPON_METAID]

    assert modules.equip.allowed_slots('weapon', meta) == {'righthand', 'lefthand', 'holster'}


@pytest.mark.parametrize('metaid', [UNKNOWN_SLOT_METAID, MISSING_SLOT_METAID])
def test_allowed_slots_armor_without_known_slot_is_empty(modules, metaid):
    assert modules.equip.allowed_slots('armor', META_INDEXED['armor'][metaid]) == set()


def test_allowed_slots_other_metatype_is_empty(modules):
    assert modules.equip.allowed_slots('race', {'_id': 1}) == set()


def test_allowed_slots_returns_a_copy(modules):
    """ Mutating the returned set must not widen the rule. """
    modules.equip.allowed_slots('weapon', {}).add('head')
    modules.equip.allowed_slots('armor', {'slot': 'Shield'}).add('head')

    assert 'head' not in modules.equip.WEAPON_SLOTS
    assert 'head' not in modules.equip.ARMOR_SLOTS['Shield']


@pytest.mark.parametrize('slotname', ARMOR_SLOTNAMES)
def test_equip_armor_in_its_own_slot_is_accepted(world, slotname):
    metaid = ARMOR_SLOT_METAIDS[slotname.capitalize()]

    code, body = world.equip('armor', slotname, metatype='armor', metaid=metaid)

    assert code == 200
    assert body['success'] is True
    assert getattr(world.creature.slots, slotname).metaid == metaid


@pytest.mark.parametrize('slotname, wrong', [
    ('feet', 'head'),
    ('hands', 'righthand'),
    ('head', 'torso'),
    ('legs', 'holster'),
    ('shoulders', 'lefthand'),
    ('torso', 'feet'),
    ])
def test_equip_armor_in_another_slot_is_400(world, slotname, wrong):
    metaid = ARMOR_SLOT_METAIDS[slotname.capitalize()]

    code, body = world.equip('armor', wrong, metatype='armor', metaid=metaid)

    _assert_refused(code, body, 400)
    assert wrong in body['msg']
    assert getattr(world.creature.slots, wrong) is None
    assert world.events == []


def test_equip_shield_in_lefthand_is_accepted(world):
    metaid = ARMOR_SLOT_METAIDS['Shield']

    code, body = world.equip('armor', 'lefthand', metatype='armor', metaid=metaid)

    assert code == 200
    assert body['success'] is True
    assert world.creature.slots.lefthand.metaid == metaid


@pytest.mark.parametrize('metaid', [ARMOR_SLOT_METAIDS['Shield'], SHIELD_2X3_METAID])
def test_equip_shield_up_to_area_6_fits_in_lefthand(world, metaid):
    """ Design ruling: a Shield fits the left hand up to 2x3 (area 6). """
    code, body = world.equip('armor', 'lefthand', metatype='armor', metaid=metaid)

    assert code == 200
    assert body['success'] is True
    assert world.creature.slots.lefthand.metaid == metaid


def test_equip_shield_2x4_does_not_fit_in_lefthand(world):
    """ Refused on purpose until the "Main gauche bouclier 2x4" perk exists. """
    code, body = world.equip('armor', 'lefthand', metatype='armor', metaid=SHIELD_2X4_METAID)

    assert code == 200
    assert body['success'] is False
    assert 'does not fit in left hand' in body['msg']
    assert world.creature.slots.lefthand is None
    assert world.events == []


def test_equip_weapon_2x3_still_does_not_fit_in_lefthand(world):
    """ The area 6 limit is for shields only: weapons keep area <= 4. """
    code, body = world.equip('weapon', 'lefthand', metaid=WEAPON_2X3_METAID)

    assert code == 200
    assert body['success'] is False
    assert 'does not fit in left hand' in body['msg']
    assert world.creature.slots.lefthand is None
    assert world.events == []


@pytest.mark.parametrize('slotname', ['righthand', 'holster', 'torso'])
def test_equip_shield_outside_lefthand_is_400(world, slotname):
    metaid = ARMOR_SLOT_METAIDS['Shield']

    code, body = world.equip('armor', slotname, metatype='armor', metaid=metaid)

    _assert_refused(code, body, 400)
    assert getattr(world.creature.slots, slotname) is None
    assert world.events == []


@pytest.mark.parametrize('slotname', ['righthand', 'lefthand', 'holster'])
def test_equip_weapon_in_a_weapon_slot_is_accepted(world, slotname):
    code, body = world.equip('weapon', slotname)

    assert code == 200
    assert body['success'] is True
    assert getattr(world.creature.slots, slotname).metaid == WEAPON_METAID


@pytest.mark.parametrize('slotname', ['head', 'torso'])
def test_equip_weapon_in_an_armor_slot_is_400(world, slotname):
    code, body = world.equip('weapon', slotname)

    _assert_refused(code, body, 400)
    assert getattr(world.creature.slots, slotname) is None
    assert world.events == []


@pytest.mark.parametrize('metaid', [UNKNOWN_SLOT_METAID, MISSING_SLOT_METAID])
def test_equip_armor_without_known_slot_is_400(world, metaid):
    """ An unknown or missing meta 'slot' is refused everywhere, never a 500. """
    code, body = world.equip('armor', 'head', metatype='armor', metaid=metaid)

    _assert_refused(code, body, 400)
    assert world.events == []


#
# unequip
#
@pytest.mark.parametrize('slotname', ['bogus', 'validate', '_data'])
def test_unequip_unknown_slotname_is_400(world, slotname):
    """ validate / _data passed the setattr() then broke save(): a 500. """
    code, body = world.unequip('weapon', slotname)

    _assert_refused(code, body, 400)
    assert world.events == []


def test_unequip_valid_slotname_reaches_the_normal_path(world):
    world.equip('armor', 'head', metatype='armor', metaid=ARMOR_METAID)
    world.events.clear()

    code, body = world.unequip('armor', 'head', metatype='armor', metaid=ARMOR_METAID)

    assert code == 200
    assert body['success'] is True
    assert world.creature.slots.head is None
    assert world.events == ['save', ('publish', 'ws-broadcast')]
