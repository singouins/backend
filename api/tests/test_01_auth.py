# -*- coding: utf8 -*-

import requests

from variables import (
    AUTH_PAYLOAD,
    API_URL,
    USER_NAME,
    )


def test_singouins_auth_register():
    response = requests.post(f'{API_URL}/auth/register', json={'password': 'plop', 'mail': USER_NAME})  # noqa: E501
    assert response.status_code == 201 or \
        'User successfully added' in response.json().get("msg")
    # Regression test: the response used to include the full Mongo user
    # document, including the bcrypt password hash.
    assert 'hash' not in response.json().get("user", {})


def test_singouins_auth_register_duplicate_does_not_leak_hash():
    # Registering the same user again hits the 409 "already exists" branch,
    # which had the exact same hash-leak bug on its own separate response.
    response = requests.post(f'{API_URL}/auth/register', json={'password': 'plop', 'mail': USER_NAME})  # noqa: E501
    assert response.status_code == 409
    assert 'hash' not in response.json().get("user", {})


def test_singouins_auth_login():
    response = requests.post(f'{API_URL}/auth/login', json=AUTH_PAYLOAD)
    assert response.status_code == 200
    assert response.json().get("access_token")
    assert response.json().get("refresh_token")


def test_singouins_auth_infos(jwt_header):
    response  = requests.get(f'{API_URL}/auth/infos', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("logged_in_as") == USER_NAME


def test_singouins_auth_refresh(jwt_header):
    response  = requests.post(f'{API_URL}/auth/refresh', headers=jwt_header['refresh'])
    assert response.status_code == 200

    new_access_token = response.json().get("access_token")
    assert new_access_token
    # A refreshed token must actually differ from the one used to log in ...
    assert new_access_token != jwt_header['access']['Authorization'].split(' ')[1]


def test_singouins_auth_refresh_token_is_usable(jwt_header):
    # Regression test: a token minted by /auth/refresh must be usable on a
    # protected route, not just returned. It used to 500 (AttributeError in
    # the JWT blocklist loader) because refresh() never registered its new
    # jti in Redis, so the revocation check found no key for it.
    response = requests.post(f'{API_URL}/auth/refresh', headers=jwt_header['refresh'])
    assert response.status_code == 200
    new_access_token = response.json().get("access_token")

    response = requests.get(
        f'{API_URL}/auth/infos',
        headers={"Authorization": f"Bearer {new_access_token}"},
        )
    assert response.status_code == 200
    assert response.json().get("logged_in_as") == USER_NAME


def test_singouins_auth_refresh_token_is_revocable():
    # Regression test: a refreshed access token must go through the exact
    # same revocation path as a login-issued one.
    response = requests.post(f'{API_URL}/auth/login', json=AUTH_PAYLOAD)
    refresh_header = {"Authorization": f"Bearer {response.json().get('refresh_token')}"}

    response = requests.post(f'{API_URL}/auth/refresh', headers=refresh_header)
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}

    response = requests.delete(f'{API_URL}/auth/logout', headers=access_header)
    assert response.status_code == 200
    assert 'JTI Revokation OK' in response.json().get("msg")

    response = requests.get(f'{API_URL}/auth/infos', headers=access_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")


def test_singouins_auth_infos_rejects_missing_token():
    response = requests.get(f'{API_URL}/auth/infos')
    assert response.status_code == 401


def test_singouins_auth_infos_rejects_garbage_token():
    response = requests.get(
        f'{API_URL}/auth/infos',
        headers={"Authorization": "Bearer not-a-real-token"},
        )
    assert response.status_code in (401, 422)


def test_singouins_auth_logout():
    # We do a manual login (no from fixture) to avoid revoking global session token
    response = requests.post(f'{API_URL}/auth/login', json=AUTH_PAYLOAD)
    access_token = response.json().get("access_token")
    access_header = {"Authorization": f"Bearer {access_token}"}

    # We check token revokation through logout
    response = requests.delete(f'{API_URL}/auth/logout', headers=access_header)
    assert response.status_code == 200
    assert 'JTI Revokation OK' in response.json().get("msg")

    # We check token is revoked and access Unauthorized
    response  = requests.get(f'{API_URL}/auth/infos', headers=access_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")


def test_singouins_auth_logout_also_revokes_refresh_token():
    # Regression test: logout used to only blocklist the access token,
    # leaving the refresh token (30-day life) usable to mint new access
    # tokens indefinitely after "logging out".
    response = requests.post(f'{API_URL}/auth/login', json=AUTH_PAYLOAD)
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    refresh_header = {"Authorization": f"Bearer {response.json().get('refresh_token')}"}

    response = requests.delete(f'{API_URL}/auth/logout', headers=access_header)
    assert response.status_code == 200
    assert 'JTI Revokation OK' in response.json().get("msg")

    response = requests.post(f'{API_URL}/auth/refresh', headers=refresh_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")

# url       = f'{API_URL}/auth/confirm/{token}'  # POST  # NOTDONE
