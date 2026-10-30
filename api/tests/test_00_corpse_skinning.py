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

# Ruling Q105 (Lordslair 2026-10-29): every dead monster leaves a Corpse in
# its instance, until the instance closes or the Corpse is skinned, and it
# may be skinned by the killer's Squad. Point 5 (ruled the same day): no
# killer, nobody skins; a killer without a Squad, the killer alone.
# A Pending invitee is not a Squad member (ruling 2026-10-10).
# Unit test: no Redis, the Corpses are real documents on an in-memory
# mongomock, so the claim (queryset delete and its count) runs for real.
REPO_PATH = os.path.join(LOCAL_PATH, os.pardir)
CORPSE_MODEL = os.path.join(REPO_PATH, 'mongo', 'models', 'Corpse.py')
MONGO_UTILS = os.path.join(REPO_PATH, 'mongo', 'utils.py')
MONGO_CONSTANTS = os.path.join(REPO_PATH, 'mongo', 'constants.py')
MOCK_ALIAS = 'test-corpse-skinning'
SKINNING_ROUTE = os.path.join(LOCAL_PATH, 'routes', 'mypc', 'action', 'profession', 'skinning.py')

INSTANCE_ID = uuid.uuid4()
OTHER_INSTANCE_ID = uuid.uuid4()
SQUAD_ID = uuid.uuid4()
OTHER_SQUAD_ID = uuid.uuid4()


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


def _creature(squad=None, rank=None, instance=INSTANCE_ID):
    """ A Creature next to the Corpse; squad None stands for no Squad. """
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        instance=instance,
        x=1,
        y=1,
        squad=types.SimpleNamespace(id=squad, rank=rank),
        stats=types.SimpleNamespace(total=types.SimpleNamespace(r=50)),
        )


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
    Loads skinning.py straight from its file (the mongo and routes.mypc
    packages connect / pull every route at import) with the real Corpse model.
    The decorators are stubbed: the view runs with g already set, as they
    would. Every credit (profession, highscores, satchel) appends to `events`.
    Killers are looked up in the `creatures` dict.
    """
    events = []
    creatures = {}

    # Corpse.py imports mongo.utils/constants: give it the real files under a stub mongo
    # package, so mongo/__init__.py (and its connect()) never runs
    package = _module('mongo', monkeypatch)
    package.__path__ = []
    monkeypatch.setitem(sys.modules, 'mongo.utils', _load('mongo.utils', MONGO_UTILS))
    monkeypatch.setitem(sys.modules, 'mongo.constants', _load('mongo.constants', MONGO_CONSTANTS))
    corpse_model = _load('test_corpse_skinning_model', CORPSE_MODEL)
    corpse_model.CorpseDocument._meta['db_alias'] = MOCK_ALIAS
    monkeypatch.setitem(sys.modules, 'mongo.models.Corpse', corpse_model)
    _module(
        'mongo.models.Creature', monkeypatch,
        CreatureDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(first=lambda: creatures.get(_id)),
            ),
        )
    _module(
        'mongo.models.Highscore', monkeypatch,
        HighscoreDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                update_one=lambda **kwargs: events.append(('highscore', _id)),
                ),
            ),
        )
    _module(
        'mongo.models.Profession', monkeypatch,
        ProfessionDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                get=lambda: types.SimpleNamespace(skinning=0),
                ),
            ),
        )
    _module(
        'mongo.models.Satchel', monkeypatch,
        SatchelDocument=types.SimpleNamespace(
            objects=lambda _id=None: types.SimpleNamespace(
                update_one=lambda **kwargs: events.append(('satchel', _id)),
                ),
            ),
        )
    pa_check = {}

    def pa(red=0, blue=0, consume=False):
        pa_check.update(red=red, blue=blue, consume=consume)
        return _identity

    _module(
        'routes._decorators', monkeypatch,
        exists=types.SimpleNamespace(creature=_identity, pa=pa),
        belongs=types.SimpleNamespace(creature_in_instance=_identity),
        )
    _module(
        'routes.mypc.action.profession._tools', monkeypatch,
        probabilistic_binary=lambda stat: 0,
        profession_gain=lambda creatureuuid, name, score: events.append(('profession', creatureuuid)),  # noqa: E501
        profession_scaled=lambda score: 0,
        )
    _module('utils.pa', monkeypatch, instance_tick=lambda creature: 3600)
    _module(
        'utils.redis', monkeypatch,
        consume_pa=lambda creatureuuid, redpa=0, bluepa=0, *, tick: events.append(
            ('pa', creatureuuid, redpa, bluepa, tick)),
        get_pa=lambda **kwargs: {'pa': 'stub'},
        )
    monkeypatch.setattr(flask_jwt_extended, 'jwt_required', lambda: _identity)

    route = _load('test_corpse_skinning_route', SKINNING_ROUTE)
    app = Flask(__name__)

    def corpse(killer, instance=INSTANCE_ID, x=1, y=1):
        """ Saves a Corpse at (1, 1); killer is a Creature, a raw id, or None. """
        killer_id = getattr(killer, 'id', killer)
        return corpse_model.CorpseDocument(
            gender=True, instance=instance, killer=killer_id,
            name='Monster', race=11, rarity='Big', x=x, y=y,
            ).save()

    def add(creature):
        """ Makes the Creature findable as a killer. """
        creatures[creature.id] = creature
        return creature

    def skin(skinner, corpse):
        with app.test_request_context():
            g.h = f'[Creature.id:{skinner.id}]'
            g.Creature = skinner
            response, code = route.skinning(creatureuuid=skinner.id, resourceuuid=corpse.id)
            return code, response.get_json()

    def exists(corpse):
        return corpse_model.CorpseDocument.objects(_id=corpse.id).count() == 1

    return types.SimpleNamespace(
        route=route, corpse=corpse, add=add, skin=skin, exists=exists, events=events,
        pa_check=pa_check,
        )


def _assert_skinned(world, skinner, corpse, code, body):
    assert code == 200
    assert body['success'] is True
    assert not world.exists(corpse)
    # Exactly 2 blue PA, once, after the claim and before any credit
    assert world.events == [
        ('pa', skinner.id, 0, 2, 3600),
        ('profession', skinner.id),
        ('highscore', skinner.id),
        ('satchel', skinner.id),
        ]


def _assert_refused(world, corpse, code, body, reason):
    assert code == 200
    assert body['success'] is False
    assert body['payload'] is None
    assert reason in body['msg']
    assert world.exists(corpse)
    # A refusal is free: no PA consumed, nothing credited
    assert world.events == []


#
# The route
#
def test_decorator_checks_pa_without_consuming(world):
    # Lordslair 2026-10-29: PA are only consumed when the action is done
    assert world.pa_check == {'red': 0, 'blue': 2, 'consume': False}


def test_out_of_range_is_refused(world):
    killer = world.add(_creature())
    killer.x = 5
    corpse = world.corpse(killer)

    code, body = world.skin(killer, corpse)

    _assert_refused(world, corpse, code, body, 'not in range')


@pytest.mark.parametrize('x, y', [(None, 1), (1, None), (None, None)])
def test_corpse_without_position_is_refused(world, x, y):
    # Lordslair 2026-10-29: the range check raised (HTTP 500) on such a Corpse
    killer = world.add(_creature())
    corpse = world.corpse(killer, x=x, y=y)

    code, body = world.skin(killer, corpse)

    _assert_refused(world, corpse, code, body, 'no position')


@pytest.mark.parametrize('attribute', ['x', 'y'])
def test_skinner_without_position_is_refused(world, attribute):
    # Same distance, same crash: a skinner without a position is refused too
    killer = world.add(_creature())
    setattr(killer, attribute, None)
    corpse = world.corpse(killer)

    code, body = world.skin(killer, corpse)

    _assert_refused(world, corpse, code, body, 'no position')


def test_killer_skins(world):
    killer = world.add(_creature(squad=SQUAD_ID, rank='Member'))
    corpse = world.corpse(killer)

    code, body = world.skin(killer, corpse)

    _assert_skinned(world, killer, corpse, code, body)


def test_killer_squad_member_skins(world):
    killer = world.add(_creature(squad=SQUAD_ID, rank='Leader'))
    member = _creature(squad=SQUAD_ID, rank='Member')
    corpse = world.corpse(killer)

    code, body = world.skin(member, corpse)

    _assert_skinned(world, member, corpse, code, body)


@pytest.mark.parametrize('squad, rank', [
    (None, None),                 # no Squad
    (OTHER_SQUAD_ID, 'Member'),   # another Squad
    (SQUAD_ID, 'Pending'),        # only invited in the killer's Squad
    ])
def test_non_member_is_refused(world, squad, rank):
    killer = world.add(_creature(squad=SQUAD_ID, rank='Leader'))
    corpse = world.corpse(killer)

    code, body = world.skin(_creature(squad=squad, rank=rank), corpse)

    _assert_refused(world, corpse, code, body, 'not skinnable')


def test_killer_without_squad_skins(world):
    # Q105 point 5 (ruled): a killer without a Squad skins alone
    killer = world.add(_creature())
    corpse = world.corpse(killer)

    code, body = world.skin(killer, corpse)

    _assert_skinned(world, killer, corpse, code, body)


@pytest.mark.parametrize('squad, rank', [
    (None, None),
    (SQUAD_ID, 'Member'),
    (SQUAD_ID, 'Leader'),
    ])
def test_killer_without_squad_nobody_else_skins(world, squad, rank):
    # Q105 point 5 (ruled): nobody else, with a Squad or without
    killer = world.add(_creature())
    corpse = world.corpse(killer)

    code, body = world.skin(_creature(squad=squad, rank=rank), corpse)

    _assert_refused(world, corpse, code, body, 'not skinnable')


@pytest.mark.parametrize('squad, rank', [
    (None, None),
    (SQUAD_ID, 'Member'),
    ])
def test_corpse_without_killer_nobody_skins(world, squad, rank):
    # Q105 point 5 (ruled): no killer, nobody, not even in the same instance
    corpse = world.corpse(None)

    code, body = world.skin(_creature(squad=squad, rank=rank), corpse)

    _assert_refused(world, corpse, code, body, 'not skinnable')


def test_corpse_of_another_instance_is_refused(world):
    killer = world.add(_creature(instance=INSTANCE_ID))
    corpse = world.corpse(killer, instance=OTHER_INSTANCE_ID)

    code, body = world.skin(killer, corpse)

    _assert_refused(world, corpse, code, body, 'not in this instance')


def test_concurrent_skinning_pays_once(world, monkeypatch):
    killer = world.add(_creature())
    corpse = world.corpse(killer)
    rule = world.route.can_skin

    def claimed_meanwhile(skinner, corpse):
        # Another skinner claims the Corpse between our read and our claim
        world.route.CorpseDocument.objects(_id=corpse.id).delete()
        return rule(skinner, corpse)

    monkeypatch.setattr(world.route, 'can_skin', claimed_meanwhile)

    code, body = world.skin(killer, corpse)

    assert code == 200
    assert body['success'] is False
    assert 'already skinned' in body['msg']
    # The loser of the claim pays nothing, PA included
    assert world.events == []


def test_only_the_claim_winner_pays(world):
    killer = world.add(_creature(squad=SQUAD_ID, rank='Leader'))
    member = _creature(squad=SQUAD_ID, rank='Member')
    corpse = world.corpse(killer)

    first = world.skin(killer, corpse)
    second = world.skin(member, corpse)

    assert first[1]['success'] is True
    assert second[1]['success'] is False
    assert [event for event in world.events if event[0] == 'pa'] == [
        ('pa', killer.id, 0, 2, 3600),
        ]


def test_skinned_corpse_is_gone(world):
    killer = world.add(_creature())
    corpse = world.corpse(killer)
    world.skin(killer, corpse)
    world.events.clear()

    code, body = world.skin(killer, corpse)

    assert code == 200
    assert body['success'] is False
    assert 'NotFound' in body['msg']
    assert world.events == []


#
# can_skin, the rule alone
#
KILLER_ID = uuid.uuid4()


def _killer(squad, rank):
    creature = _creature(squad=squad, rank=rank)
    creature.id = KILLER_ID
    return creature


@pytest.mark.parametrize('killer, skinner, expected', [
    # The killer itself, whatever its Squad
    (_killer(SQUAD_ID, 'Member'), 'killer', True),
    (_killer(None, None), 'killer', True),
    (_killer(SQUAD_ID, 'Pending'), 'killer', True),
    # A member of the killer's Squad
    (_killer(SQUAD_ID, 'Leader'), _creature(SQUAD_ID, 'Member'), True),
    (_killer(SQUAD_ID, 'Member'), _creature(SQUAD_ID, None), True),
    # Not a member of it
    (_killer(SQUAD_ID, 'Leader'), _creature(SQUAD_ID, 'Pending'), False),
    (_killer(SQUAD_ID, 'Leader'), _creature(OTHER_SQUAD_ID, 'Member'), False),
    (_killer(SQUAD_ID, 'Leader'), _creature(None, None), False),
    # The killer has no Squad (or is only invited): the killer alone
    (_killer(None, None), _creature(None, None), False),
    (_killer(None, None), _creature(SQUAD_ID, 'Member'), False),
    (_killer(SQUAD_ID, 'Pending'), _creature(SQUAD_ID, 'Member'), False),
    # No killer: nobody
    (None, _creature(SQUAD_ID, 'Member'), False),
    (None, _creature(None, None), False),
    # A killer Creature that no longer exists: nobody but itself
    ('unknown', _creature(SQUAD_ID, 'Member'), False),
    ])
def test_can_skin(world, killer, skinner, expected):
    if killer == 'unknown':
        corpse = types.SimpleNamespace(killer=KILLER_ID)
    elif killer is None:
        corpse = types.SimpleNamespace(killer=None)
    else:
        world.add(killer)
        corpse = types.SimpleNamespace(killer=killer.id)
    if skinner == 'killer':
        skinner = killer

    assert world.route.can_skin(skinner, corpse) is expected
