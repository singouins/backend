# -*- coding: utf8 -*-

import pytest
import requests

from variables import AUTH_API_URL, AUTH_PAYLOAD, API_URL, CREATURE_ID


@pytest.fixture(scope="session")
def jwt_header():
    header = {}
    # auth/* is a separate service now. api's own suite doesn't depend on
    # auth's suite having run first (or at all) to create the shared test
    # account - register it here too, tolerating "already exists" (409),
    # so this fixture is self-sufficient regardless of run order.
    requests.post(f'{AUTH_API_URL}/register', json={'mail': AUTH_PAYLOAD['username'], 'password': AUTH_PAYLOAD['password']})  # noqa: E501

    # Perform the login call and get the token
    response = requests.post(f'{AUTH_API_URL}/login', json=AUTH_PAYLOAD)
    assert response.status_code == 200

    access_token = response.json().get("access_token")
    assert access_token is not None  # Ensure the token is present

    refresh_token = response.json().get("refresh_token")
    assert refresh_token is not None  # Ensure the token is present

    header = {
        "access": {"Authorization": f"Bearer {access_token}"},
        "refresh": {"Authorization": f"Bearer {refresh_token}"}
    }
    # Return the token so it can be used in other tests
    return header


@pytest.fixture(scope="function")
def mypc(jwt_header):
    # Perform the login call and get the Creatures list
    response = requests.get(f'{API_URL}/mypc', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("success") is True

    raw_list = response.json().get("payload")
    assert isinstance(raw_list, list)

    indexed_list = {pc["_id"]: pc for pc in raw_list}

    # Return the data so it can be used in other tests
    return {'indexed': indexed_list, 'raw': raw_list}


@pytest.fixture(scope="function")
def myitems(jwt_header):
    # Perform the login call and get the Creatures list
    response = requests.get(f'{API_URL}/mypc/{CREATURE_ID}/item', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("success") is True

    # Return the data so it can be used in other tests
    return response.json().get("payload")
