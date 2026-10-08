# -*- coding: utf8 -*-

import datetime
import pytest
import requests
import uuid

from variables import (
    API_ENV,
    API_URL,
    CREATURE_ID,
    CREATURE_NAME,
    INTERNAL_TOKEN,
    r,
    )

# POST /internal/instance/<instanceId>/creature/<creatureId>/eject is called
# by the fight resolver when a Singouin dies. It is service-to-service (shared
# token, no JWT), idempotent and state-based: the creature is ejected through
# leave_instance() only if it is in exactly <instanceId>, otherwise nothing is
# touched and the answer is {"result": "gone"}.
#
# Start state (after test_13): PJTest is out of any instance, and the PC
# named 'PJTestInstanceJoin' sits alone in its own instance (PJTest is a
# recorded leaver of it, so it cannot join it). End state must be the same.

pytestmark = pytest.mark.skipif(INTERNAL_TOKEN is None, reason='SEP_INTERNAL_TOKEN not set')

INTERNAL_HEADER = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
BLUE_KEY = f"{API_ENV}:pas:{CREATURE_ID}:blue"
BODY = {"mapid": 1, "hardcore": True, "fast": False, "public": True}
ACTIVE = {
    "bearer": CREATURE_ID,
    "duration_base": 60,
    "name": 'PyTest',
    "type": 'effect',
    }


def eject_url(instance_id, creature_id):
    return f"{API_URL}/internal/instance/{instance_id}/creature/{creature_id}/eject"


def body(by=None):
    """ A fresh eject request, as the resolver sends it. """
    return {
        "reason": 'death',
        "by": by,
        "at": datetime.datetime.utcnow().isoformat(),
        "requestId": str(uuid.uuid4()),
        }


def _pcjoin(mypc):
    return [x for x in mypc['raw'] if x['name'] == 'PJTestInstanceJoin'][0]


def test_singouins_internal_eject_requires_token():
    url = eject_url(uuid.uuid4(), uuid.uuid4())

    response = requests.post(url, json=body())
    assert response.status_code == 401
    assert response.json().get("success") is False

    response = requests.post(url, headers={"Authorization": "Bearer not-the-token"}, json=body())
    assert response.status_code == 403
    assert response.json().get("success") is False


def test_singouins_internal_eject_malformed_is_400():
    response = requests.post(eject_url('not-a-uuid', uuid.uuid4()), headers=INTERNAL_HEADER, json=body())  # noqa: E501
    assert response.status_code == 400
    assert response.json().get("success") is False

    response = requests.post(eject_url(uuid.uuid4(), 'not-a-uuid'), headers=INTERNAL_HEADER, json=body())  # noqa: E501
    assert response.status_code == 400
    assert response.json().get("success") is False

    response = requests.post(eject_url(uuid.uuid4(), uuid.uuid4()), headers=INTERNAL_HEADER, json={})  # noqa: E501
    assert response.status_code == 400
    assert response.json().get("success") is False
    assert response.json().get("msg") == 'Validation and parsing error'

    # A JSON body that is not an object
    response = requests.post(eject_url(uuid.uuid4(), uuid.uuid4()), headers=INTERNAL_HEADER, json=[])  # noqa: E501
    assert response.status_code == 400
    assert response.json().get("success") is False
    assert response.json().get("msg") == 'JSON object expected'


def test_singouins_internal_eject_unknown_creature_is_gone(mypc):
    pcjoin = _pcjoin(mypc)

    response = requests.post(eject_url(pcjoin['instance'], uuid.uuid4()), headers=INTERNAL_HEADER, json=body())  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True
    assert response.json().get("payload") == {"result": 'gone'}


def test_singouins_internal_eject_wrong_instance_is_gone_and_touches_nothing(jwt_header, mypc):
    assert 'instance' not in mypc['indexed'][CREATURE_ID]
    pcjoin = _pcjoin(mypc)

    # PJTest opens its own instance
    response = requests.put(f'{API_URL}/mypc/{CREATURE_ID}/instance', headers=jwt_header['access'], json=BODY)  # noqa: E501
    assert response.status_code == 201
    assert response.json().get("success") is True
    instance_id = response.json().get("payload")['_id']

    # Simulate spent PA and an active in that instance
    r.set(BLUE_KEY, 'None', ex=9000)
    active_key = f"{API_ENV}:{instance_id}:effects:{CREATURE_ID}:PyTest"
    r.hset(active_key, mapping=ACTIVE)
    r.expire(active_key, 9000)

    # A late retry naming another instance must never eject from the current one
    response = requests.post(eject_url(pcjoin['instance'], CREATURE_ID), headers=INTERNAL_HEADER, json=body(by=pcjoin['_id']))  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True
    assert response.json().get("payload") == {"result": 'gone'}

    response = requests.get(f'{API_URL}/mypc', headers=jwt_header['access'])
    assert response.status_code == 200
    pc = [x for x in response.json().get("payload") if x['name'] == CREATURE_NAME][0]
    assert pc['instance'] == instance_id
    assert r.exists(BLUE_KEY) == 1
    assert r.exists(active_key) == 1


def test_singouins_internal_eject_closes_and_is_idempotent(jwt_header, mypc):
    instance_id = mypc['indexed'][CREATURE_ID]['instance']
    pcjoin = _pcjoin(mypc)
    assert instance_id != pcjoin['instance']
    request = body(by=pcjoin['_id'])

    # PJTest is alone in its instance: ejecting it closes the instance
    response = requests.post(eject_url(instance_id, CREATURE_ID), headers=INTERNAL_HEADER, json=request)  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True
    assert response.json().get("payload") == {"result": 'closed'}

    response = requests.get(f'{API_URL}/mypc', headers=jwt_header['access'])
    assert response.status_code == 200
    pc = [x for x in response.json().get("payload") if x['name'] == CREATURE_NAME][0]
    assert 'instance' not in pc

    # Outside an instance nothing of the creature exists in Redis,
    # and a closed instance takes every key scoped by it
    assert r.keys(f"{API_ENV}:pas:{CREATURE_ID}:*") == []
    assert r.keys(f"{API_ENV}:{instance_id}:*") == []
    assert r.keys(f"{instance_id}:*") == []

    # The resolver may retry the exact same request: nothing left to eject
    response = requests.post(eject_url(instance_id, CREATURE_ID), headers=INTERNAL_HEADER, json=request)  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True
    assert response.json().get("payload") == {"result": 'gone'}

    # PJTestInstanceJoin was never concerned
    response = requests.get(f'{API_URL}/mypc', headers=jwt_header['access'])
    assert [x for x in response.json().get("payload") if x['name'] == 'PJTestInstanceJoin'][0]['instance'] == pcjoin['instance']  # noqa: E501


def test_singouins_internal_eject_monster_is_400(jwt_header, mypc):
    assert 'instance' not in mypc['indexed'][CREATURE_ID]

    # Mobs are spawned by the instance creation at random coordinates with no
    # name/id route to find them, so one is picked from PJTest's view (range
    # limited); when none is in sight the check is skipped, not failed
    response = requests.put(f'{API_URL}/mypc/{CREATURE_ID}/instance', headers=jwt_header['access'], json=BODY)  # noqa: E501
    assert response.status_code == 201
    assert response.json().get("success") is True
    instance_id = response.json().get("payload")['_id']

    try:
        response = requests.get(f'{API_URL}/mypc/{CREATURE_ID}/view', headers=jwt_header['access'])
        assert response.status_code == 200
        assert response.json().get("success") is True
        mobs = [x for x in response.json().get("payload")['creatures'] if 'account' not in x]
        if not mobs:
            pytest.skip('no mob in view')

        response = requests.post(eject_url(instance_id, mobs[0]['_id']), headers=INTERNAL_HEADER, json=body(by=CREATURE_ID))  # noqa: E501
        assert response.status_code == 400
        assert response.json().get("success") is False
        assert 'no account' in response.json().get("msg")
    finally:
        # Restore the start state: PJTest out of any instance
        response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/instance/{instance_id}/leave", headers=jwt_header['access'])  # noqa: E501
        assert response.status_code == 200
        assert response.json().get("success") is True

    response = requests.get(f'{API_URL}/mypc', headers=jwt_header['access'])
    assert response.status_code == 200
    pc = [x for x in response.json().get("payload") if x['name'] == CREATURE_NAME][0]
    assert 'instance' not in pc
