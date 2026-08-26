# -*- coding: utf8 -*-

import json
import os
import time
import uuid

import pytest
import redis
import requests

from mongo.models.Creature import (
    CreatureDocument,
    CreatureHP,
    CreatureKorp,
    CreatureSlots,
    CreatureSquad,
    CreatureStats,
    CreatureStatsType,
    )
from mongo.models.Instance import InstanceDocument

# Redis variables
REDIS_HOST = os.environ.get("REDIS_HOST", '127.0.0.1')
REDIS_PORT = os.environ.get("REDIS_PORT", 6379)
REDIS_BASE = os.environ.get("REDIS_BASE", 0)

# Must mirror ai/variables.py's env_vars['CREATURE_PATH'] so we publish on
# the exact channel the running `ai` app (started by CI before this test
# suite runs) is subscribed to.
API_ENV = os.environ.get("API_ENV", "")
CREATURE_PATH = f'ai-creature-{API_ENV.lower()}'

# Where the app's Flask API is reachable (see ai/main.py)
APP_URL = 'http://127.0.0.1:5000'

WAIT_TIMEOUT = 10
WAIT_INTERVAL = 0.5

INSTANCE_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")
CREATURE_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")

r = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_BASE,
    encoding='utf-8',
    decode_responses=True,
    )


def _zero_stats():
    zero = CreatureStatsType(b=0, g=0, m=0, p=0, r=0, v=0)
    return CreatureStats(race=zero, spec=zero, total=zero)


@pytest.fixture
def creature():
    """
    Inserts a real Instance + Creature (race=14 -> Salamander, see
    utils/actions.py:creature_pop) so the running app can actually resolve
    the creature it is told to pop, then cleans up afterwards.
    """
    Instance = InstanceDocument(
        _id=INSTANCE_UUID,
        creator=uuid.uuid4(),
        map=1,
        tick=3600,
        ).save()
    Creature = CreatureDocument(
        _id=CREATURE_UUID,
        instance=INSTANCE_UUID,
        name="PyTest Creature",
        race=14,
        gender=True,
        hp=CreatureHP(base=10, current=10, max=10),
        korp=CreatureKorp(),
        slots=CreatureSlots(),
        squad=CreatureSquad(),
        stats=_zero_stats(),
        x=100,
        y=100,
        ).save()

    yield Creature

    Creature.delete()
    Instance.delete()


def _publish(action, creature_doc):
    # creature_pop()/creature_kill() (ai/utils/actions.py) call
    # json.loads(data['creature']) themselves, so - matching how
    # creature_init() publishes - the "creature" field must be the JSON
    # *string* from to_json(), not a parsed dict.
    r.publish(
        CREATURE_PATH,
        json.dumps({
            "action": action,
            "creature": creature_doc.to_json(),
            })
        )


def _threads():
    response = requests.get(f'{APP_URL}/threads', timeout=(1, 1))
    assert response.status_code == 200
    return response.json()['payload']


def _wait_until(predicate, timeout=WAIT_TIMEOUT, interval=WAIT_INTERVAL):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f'Condition not met within {timeout}s (last check: {last})')


def test_check_get():
    response = requests.get(f'{APP_URL}/check', timeout=(1, 1))
    assert response.status_code == 200
    assert response.json()['success'] is True


def test_creature_pop_spawns_a_thread(creature):
    _publish('pop', creature)

    threads = _wait_until(
        lambda: [t for t in _threads() if t['id'] == str(CREATURE_UUID)]
        )
    assert threads[0]['creature']['name'] == "PyTest Creature"

    # Cleanup: kill it so it does not leak into the next test
    _publish('kill', creature)
    _wait_until(
        lambda: not [t for t in _threads() if t['id'] == str(CREATURE_UUID)]
        )


def test_creature_kill_removes_the_thread(creature):
    _publish('pop', creature)
    _wait_until(
        lambda: [t for t in _threads() if t['id'] == str(CREATURE_UUID)]
        )

    _publish('kill', creature)

    _wait_until(
        lambda: not [t for t in _threads() if t['id'] == str(CREATURE_UUID)]
        )


def test_creature_pop_unknown_creature_is_ignored():
    """
    Popping a creature that does not exist in MongoDB must not spawn a
    thread (creature_pop() should hit the DoesNotExist branch and return).
    """
    unknown_uuid = str(uuid.uuid4())
    r.publish(
        CREATURE_PATH,
        json.dumps({
            "action": 'pop',
            "creature": json.dumps({"_id": unknown_uuid, "name": "Ghost"}),
            })
        )

    time.sleep(WAIT_TIMEOUT / 2)
    assert not [t for t in _threads() if t['id'] == unknown_uuid]
