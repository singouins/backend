# -*- coding: utf8 -*-

import pytest
import requests

from variables import AUTH_PAYLOAD, API_URL


@pytest.fixture(scope="session")
def jwt_header():
    header = {}
    # Perform the login call and get the token
    response = requests.post(f'{API_URL}/login', json=AUTH_PAYLOAD)
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
