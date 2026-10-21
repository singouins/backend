# -*- coding: utf8 -*-

import requests

from variables import (
    API_ENV,
    API_URL,
    CREATURE_ID,
    r,
    )

# Crafting (recycling, tanning, catalyze, craft consumable) is only possible in town,
# i.e. when the Creature is NOT in an Instance.
REFUSAL_MSG = 'only possible in town'


def test_singouins_crafting_refused_in_instance(jwt_header, myitems):
    # Any existing Item is enough: the refusal fires before the Item lookup
    item = myitems['weapon'][0]

    # PJTest creates an Instance
    BODY = {"mapid": 1, "hardcore": True, "fast": False, "public": True}
    response  = requests.put(f'{API_URL}/mypc/{CREATURE_ID}/instance', headers=jwt_header['access'], json=BODY)  # noqa: E501
    assert response.status_code == 201
    assert response.json().get("success") is True
    instance_id = response.json().get("payload")['_id']

    # Recycling is refused
    response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/action/profession/recycling/{item['_id']}", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is False
    assert REFUSAL_MSG in response.json().get("msg")

    # Tanning is refused
    response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/action/profession/tanning", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is False
    assert REFUSAL_MSG in response.json().get("msg")

    # Catalyze is refused
    response = requests.put(f"{API_URL}/mypc/{CREATURE_ID}/action/item/catalyze/{item['_id']}", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is False
    assert REFUSAL_MSG in response.json().get("msg")

    # Craft consumable is refused
    response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/action/craft/consumable/2", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is False
    assert REFUSAL_MSG in response.json().get("msg")

    # PJTest leaves the Instance
    response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/instance/{instance_id}/leave", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert response.json().get("success") is True


def test_singouins_crafting_allowed_out_of_instance(jwt_header, mypc):
    assert 'instance' not in mypc['indexed'][CREATURE_ID]

    # Tanning is not refused by the crafting gate
    # (it may still fail for lack of skins, we only assert on the gate)
    response = requests.post(f"{API_URL}/mypc/{CREATURE_ID}/action/profession/tanning", headers=jwt_header['access'])  # noqa: E501
    assert response.status_code == 200
    assert REFUSAL_MSG not in response.json().get("msg")

    # Outside of an Instance, no PA is consumed
    assert r.exists(f"{API_ENV}:pas:{CREATURE_ID}:red") == 0
    assert r.exists(f"{API_ENV}:pas:{CREATURE_ID}:blue") == 0
