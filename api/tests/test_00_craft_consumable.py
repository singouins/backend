# -*- coding: utf8 -*-

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

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# Design ruling Q78 (2026-10-21): consumables meta 2 (fast heal) and 3 (long
# heal) are crafted in town with the 'craft_potion' recipe (25 banana + 1
# broken shard), one unit per craft, into Satchel.consumable.fast / .long.
# Meta 1 (standard heal) is plain currency and is never crafted.
# Unit test: no Redis, Mongo is an in-memory mongomock behind mongoengine,
# so the conditional update and its $inc run for real.
REPO_PATH = os.path.join(LOCAL_PATH, os.pardir)
SATCHEL_MODEL = os.path.join(REPO_PATH, 'mongo', 'models', 'Satchel.py')
CRAFT_ROUTE = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'action', 'craft', 'consumable.py')

CREATURE_ID = uuid.uuid4()
TICK = 3600


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
    Loads the real Satchel model and the route straight from their files (the
    mongo and routes.mypc packages connect / pull every route at import).
    The decorators and utils.redis are stubbed: the view runs with g already
    set, as the decorators would.
    """
    satchel_model = _load('mongo.models.Satchel', SATCHEL_MODEL)
    monkeypatch.setitem(sys.modules, 'mongo.models.Satchel', satchel_model)

    decorators = types.ModuleType('routes._decorators')
    decorators.exists = types.SimpleNamespace(
        creature=_identity,
        pa=lambda red=0, blue=0, consume=False: _identity,
        )
    decorators.belongs = types.SimpleNamespace(creature_out_of_instance=_identity)
    monkeypatch.setitem(sys.modules, 'routes._decorators', decorators)

    redis_stub = types.ModuleType('utils.redis')
    redis_stub.get_pa = None
    redis_stub.consume_pa = None
    monkeypatch.setitem(sys.modules, 'utils.redis', redis_stub)

    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    route = _load('test_craft_consumable_route', CRAFT_ROUTE)
    return types.SimpleNamespace(route=route, model=satchel_model)


@pytest.fixture
def mongo():
    """ In-memory Mongo for the mongoengine default alias, dropped after the test. """
    mongoengine.connect(
        'pytest', alias='default', mongo_client_class=mongomock.MongoClient,
        uuidRepresentation='standard',
        )
    yield
    mongoengine.disconnect(alias='default')


@pytest.fixture
def world(modules, mongo, monkeypatch):
    """
    Calls the view in a request context with g.Creature set. consume_pa and
    get_pa calls are recorded in `events`.
    """
    events = []
    creature = types.SimpleNamespace(id=CREATURE_ID, instance=None)

    monkeypatch.setattr(modules.route, 'instance_tick', lambda creature: TICK)
    monkeypatch.setattr(
        modules.route, 'consume_pa', lambda **kwargs: events.append(('consume_pa', kwargs)),
        )
    monkeypatch.setattr(modules.route, 'get_pa', lambda **kwargs: {'pa': 'stub'})

    app = Flask(__name__)
    model = modules.model

    def satchel(banana=0, broken=0, consumable=True):
        """ Saves the Creature Satchel; consumable=False stands for a pre-Q78 one. """
        document = model.SatchelDocument(
            _id=CREATURE_ID,
            ammo=model.SatchelAmmo(),
            currency=model.SatchelCurrency(banana=banana),
            resource=model.SatchelResource(),
            shard=model.SatchelShard(broken=broken),
            )
        if consumable:
            document.consumable = model.SatchelConsumable()
        document.save()
        return document

    def raw():
        """ The stored Satchel as Mongo holds it (UUIDField binary=False: a string _id). """
        return model.SatchelDocument._get_collection().find_one({'_id': str(CREATURE_ID)})

    def craft(metaid):
        with app.test_request_context():
            g.h = f'[Creature.id:{CREATURE_ID}]'
            g.Creature = creature
            response, code = modules.route.consumable(creatureuuid=CREATURE_ID, metaid=metaid)
            return code, response.get_json()

    return types.SimpleNamespace(craft=craft, satchel=satchel, raw=raw, events=events)


def _assert_refused_400(code, body):
    assert code == 400
    assert body['success'] is False
    assert body['payload'] is None


#
# Path parameter checks
#
def test_craft_standard_consumable_is_400(world):
    """ Meta 1 is plain currency: never crafted, nothing spent. """
    world.satchel(banana=100, broken=5)
    before = world.raw()

    code, body = world.craft(1)

    _assert_refused_400(code, body)
    assert 'never crafted' in body['msg']
    assert world.raw() == before
    assert world.events == []


@pytest.mark.parametrize('metaid', [0, 4, 999])
def test_craft_unknown_consumable_is_400(world, metaid):
    world.satchel(banana=100, broken=5)
    before = world.raw()

    code, body = world.craft(metaid)

    _assert_refused_400(code, body)
    assert 'unknown' in body['msg']
    assert world.raw() == before
    assert world.events == []


#
# Craft
#
@pytest.mark.parametrize('metaid, kind, other', [(2, 'fast', 'long'), (3, 'long', 'fast')])
def test_craft_increments_its_kind_and_pays_the_recipe(world, metaid, kind, other):
    world.satchel(banana=30, broken=2)

    code, body = world.craft(metaid)

    assert code == 200
    assert body['success'] is True
    stored = world.raw()
    assert stored['consumable'][kind] == 1
    assert stored['consumable'][other] == 0
    assert stored['currency']['banana'] == 5
    assert stored['shard']['broken'] == 1
    assert body['payload']['satchel']['consumable'][kind] == 1
    assert body['payload']['pa'] == {'pa': 'stub'}
    assert world.events == [
        ('consume_pa', {'creatureuuid': CREATURE_ID, 'bluepa': 2, 'redpa': 0, 'tick': TICK}),
        ]


def test_craft_twice_stacks(world):
    world.satchel(banana=50, broken=2)

    world.craft(2)
    code, body = world.craft(2)

    assert code == 200
    assert body['success'] is True
    stored = world.raw()
    assert stored['consumable']['fast'] == 2
    assert stored['currency']['banana'] == 0
    assert stored['shard']['broken'] == 0


def test_craft_on_a_satchel_without_consumable_creates_it(world):
    """ Satchels created before Q78 have no consumable field: $inc creates the path. """
    world.satchel(banana=25, broken=1, consumable=False)
    assert 'consumable' not in world.raw()

    code, body = world.craft(3)

    assert code == 200
    assert body['success'] is True
    stored = world.raw()
    assert stored['consumable'] == {'long': 1}
    assert stored['currency']['banana'] == 0
    assert stored['shard']['broken'] == 0


@pytest.mark.parametrize('banana, broken', [(24, 1), (25, 0), (0, 0)])
def test_craft_without_enough_resources_is_refused(world, banana, broken):
    """ Nothing written, no PA spent, house style 200 / success False. """
    world.satchel(banana=banana, broken=broken)
    before = world.raw()

    code, body = world.craft(2)

    assert code == 200
    assert body['success'] is False
    assert 'Not enough' in body['msg']
    assert body['payload']['satchel']['currency']['banana'] == banana
    assert world.raw() == before
    assert world.events == []


def test_craft_without_satchel_is_404(world):
    code, body = world.craft(2)

    assert code == 404
    assert body['success'] is False
    assert world.events == []
