# -*- coding: utf8 -*-

import datetime
import os
import sys
import urllib.parse
import uuid

import pymongo
import pytest
import requests

# api/ on sys.path for utils.xp, whatever the cwd pytest runs from
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from variables import (  # noqa: E402
    API_URL,
    CREATURE_ID,
    INTERNAL_TOKEN,
    )

# POST /internal/instance/<instanceId>/creature/<creatureId>/remove is called
# by the fight resolver when a monster dies. Against the running api and a
# real Mongo, this checks what the unit tests (test_00_internal_remove.py)
# only stub: the monster and its Corpse, the killer's XP (level-up included),
# its kill / xp highscores, and that a retry changes nothing.
#
# Mobs are spawned by the instance creation at random coordinates with no
# route listing them all, so they are read straight from Mongo (as
# test_00_mongo.py connects): only to pick one and to check its Corpse,
# everything else goes through the api.
#
# Start state (after test_15_internal_eject): PJTest is out of any instance.
# End state: the same, PJTest having gained the kill's XP.

pytestmark = pytest.mark.skipif(INTERNAL_TOKEN is None, reason='SEP_INTERNAL_TOKEN not set')

INTERNAL_HEADER = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
BODY = {"mapid": 1, "hardcore": True, "fast": False, "public": True}


@pytest.fixture(scope='module')
def db():
    """ The game database, through pymongo (read-only use). """
    uri = 'mongodb://%s:%s@%s/%s?authSource=admin' % (
        urllib.parse.quote_plus(os.environ.get("MONGO_USER", 'singouins')),
        urllib.parse.quote_plus(os.environ.get("MONGO_PASS")),
        os.environ.get("MONGO_HOST", '127.0.0.1'),
        os.environ.get("MONGO_BASE", 'singouins'),
        )
    client = pymongo.MongoClient(uri)
    yield client[os.environ.get("MONGO_BASE", 'singouins')]
    client.close()


def remove_url(instance_id, creature_id):
    return f"{API_URL}/internal/instance/{instance_id}/creature/{creature_id}/remove"


def body(by=None, assists=None):
    """ A fresh remove request, as the resolver sends it. """
    request = {
        "reason": 'death',
        "by": by,
        "at": datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat(),
        "requestId": str(uuid.uuid4()),
        }
    if assists is not None:
        request['assists'] = assists
    return request


def _pjtest(jwt_header):
    response = requests.get(f'{API_URL}/mypc', headers=jwt_header['access'])
    assert response.status_code == 200
    return [x for x in response.json().get("payload") if x['_id'] == CREATURE_ID][0]


def _general(jwt_header):
    response = requests.get(f'{API_URL}/mypc/{CREATURE_ID}/highscores', headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True
    return response.json().get("payload")['general']


@pytest.fixture
def instance(jwt_header, mypc):
    """
    PJTest opens its own instance (which spawns its mobs); left again after
    the test, whatever happens, to restore the start state.
    """
    assert 'instance' not in mypc['indexed'][CREATURE_ID]
    response = requests.put(f'{API_URL}/mypc/{CREATURE_ID}/instance', headers=jwt_header['access'], json=BODY)  # noqa: E501
    assert response.status_code == 201
    assert response.json().get("success") is True
    instance_id = response.json().get("payload")['_id']
    try:
        yield instance_id
    finally:
        response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/instance/{instance_id}/leave", headers=jwt_header['access'])  # noqa: E501
        assert response.status_code == 200
        assert response.json().get("success") is True


def test_singouins_internal_remove_requires_token():
    url = remove_url(uuid.uuid4(), uuid.uuid4())

    response = requests.post(url, json=body())
    assert response.status_code == 401

    response = requests.post(url, headers={"Authorization": "Bearer not-the-token"}, json=body())
    assert response.status_code == 403


def test_singouins_internal_remove_unknown_instance_is_404():
    response = requests.post(remove_url(uuid.uuid4(), uuid.uuid4()), headers=INTERNAL_HEADER, json=body())  # noqa: E501
    assert response.status_code == 404
    assert response.json().get("success") is False


def test_singouins_internal_remove_unknown_creature_is_gone(instance):
    response = requests.post(remove_url(instance, uuid.uuid4()), headers=INTERNAL_HEADER, json=body())  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("payload") == {"result": 'gone'}


def test_singouins_internal_remove_singouin_is_400(instance):
    response = requests.post(remove_url(instance, CREATURE_ID), headers=INTERNAL_HEADER, json=body())  # noqa: E501
    assert response.status_code == 400
    assert 'use eject' in response.json().get("msg")


def test_singouins_internal_remove_kill_pays_the_killer_once(jwt_header, db, instance):
    from mongo.constants import CREATURE_RARITY
    from utils.xp import apply_xp, xp_gain

    monsters = list(db.creatures.find({"instance": instance, "account": None}))
    assert monsters, 'the instance creation spawned no mob'
    # The rarest one: from level 1, anything but a Small levels PJTest up, so
    # the level-up is almost always exercised (rarities are random)
    monster = max(monsters, key=lambda mob: CREATURE_RARITY[mob['rarity']]['xp_mult'])
    monster_id = monster['_id']

    before = _pjtest(jwt_header)
    general = _general(jwt_header)
    # Solo kill: the gain and level-up the curve gives (utils/xp.py, unit-tested)
    gain = xp_gain(before['level'], monster['level'], monster['rarity'], 1)
    level, xp = apply_xp(before['level'], before['xp'], gain)
    assert gain > 0

    # PJTest is repeated in the assists and an unknown id is there too: both
    # are cleaned, PJTest is paid once and as the killer
    request = body(by=CREATURE_ID, assists=[CREATURE_ID, str(uuid.uuid4())])
    response = requests.post(remove_url(instance, monster_id), headers=INTERNAL_HEADER, json=request)  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True
    assert response.json().get("payload") == {"result": 'removed'}

    # The monster is gone, its Corpse is there with PJTest as the killer
    assert db.creatures.find_one({"_id": monster_id}) is None
    corpse = db.corpses.find_one({"_id": monster_id})
    assert corpse is not None
    assert corpse['killer'] == CREATURE_ID
    assert corpse['instance'] == instance

    # The XP, through the api
    after = _pjtest(jwt_header)
    assert (after['level'], after['xp']) == (level, xp)

    # Highscores: one kill, the gain, no assist (PJTest was the killer)
    assert _general(jwt_header) == {
        **general,
        'kill': general['kill'] + 1,
        'xp': general['xp'] + gain,
        }

    # The resolver may retry the exact same request: nothing more is paid
    response = requests.post(remove_url(instance, monster_id), headers=INTERNAL_HEADER, json=request)  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("payload") == {"result": 'gone'}
    assert _pjtest(jwt_header)['xp'] == xp
    assert _general(jwt_header)['kill'] == general['kill'] + 1
