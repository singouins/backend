# -*- coding: utf8 -*-

# PA pools only exist inside an Instance (designer ruling, 2026-10-08).
# Runs after test_11_instance.py: PJTest is out of any Instance at that point
# (PJTestInstanceJoin sits in its own Instance and is left alone here).
#
# The Instance created below keeps InstanceDocument.tick's default (3600s):
# red regenerates 1 PA per tick (3600s), blue 1 PA per 2 ticks (7200s).

import requests

from variables import (
    API_ENV,
    API_URL,
    CREATURE_ID,
    r,
    )

INSTANCE_BODY = {"mapid": 1, "hardcore": True, "fast": False, "public": True}

RED_KEY  = f"{API_ENV}:pas:{CREATURE_ID}:red"
BLUE_KEY = f"{API_ENV}:pas:{CREATURE_ID}:blue"

# Simulated spent PA, set directly the way consume_pa() does (key = 'None', TTL = time
# left until the pool is full again). PA are read by functions_pa pa_read: a PA only
# counts once fully regenerated. TTLs are chosen away from exact multiples of the
# duration, so a few seconds of drift never move the count:
#   blue, 9000s left, duration 7200: 8 - ceil(9000 / 7200) = 6 PA,
#         next PA in (9000 - 1) % 7200 + 1 = 1800s
#   red,  5000s left, duration 3600: 16 - ceil(5000 / 3600) = 14 PA,
#         next PA in (5000 - 1) % 3600 + 1 = 1400s
BLUE_TTL = 9000
RED_TTL  = 5000


def test_singouins_pa_instance_create(jwt_header):
    response = requests.put(f'{API_URL}/mypc/{CREATURE_ID}/instance', headers=jwt_header['access'], json=INSTANCE_BODY)  # noqa: E501
    assert response.status_code == 201
    assert response.json().get("success") is True
    assert response.json().get("payload")['_id'] is not None


def test_singouins_pa_instance_full_pools(jwt_header):
    response = requests.get(f'{API_URL}/mypc/{CREATURE_ID}/pa', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("success") is True

    payload = response.json().get("payload")
    assert payload['red']['pa'] == 16
    assert payload['red']['ttnpa'] == 0
    assert payload['blue']['pa'] == 8
    assert payload['blue']['ttnpa'] == 0


def test_singouins_pa_instance_spent_pools(jwt_header):
    r.set(BLUE_KEY, 'None', ex=BLUE_TTL)
    r.set(RED_KEY, 'None', ex=RED_TTL)

    response = requests.get(f'{API_URL}/mypc/{CREATURE_ID}/pa', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("success") is True

    # A few seconds may elapse between the SET and the read: ttnpa only shrinks
    payload = response.json().get("payload")
    assert payload['blue']['pa'] == 6
    assert 1790 < payload['blue']['ttnpa'] <= 1800
    assert payload['red']['pa'] == 14
    assert 1390 < payload['red']['ttnpa'] <= 1400


def test_singouins_pa_instance_leave(jwt_header, mypc):
    instance_id = mypc['indexed'][CREATURE_ID]['instance']

    response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/instance/{instance_id}/leave", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True


def test_singouins_pa_outside_instance_after_leave(jwt_header):
    response = requests.get(f'{API_URL}/mypc/{CREATURE_ID}/pa', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("success") is True
    assert response.json().get("payload") is None


def test_singouins_pa_instance_reset():
    r.delete(BLUE_KEY)
    r.delete(RED_KEY)
