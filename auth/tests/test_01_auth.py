# -*- coding: utf8 -*-

import secrets

import requests

from variables import (
    API_ENV,
    AUTH_PAYLOAD,
    API_URL,
    r,
    USER_NAME,
    )


def test_singouins_auth_register():
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': USER_NAME})  # noqa: E501
    assert response.status_code == 201 or \
        'User successfully added' in response.json().get("msg")
    # Regression test: the response used to include the full Mongo user
    # document, including the bcrypt password hash.
    assert 'hash' not in response.json().get("user", {})


def test_singouins_auth_register_rejects_invalid_email():
    # Regression test: `mail` used to be a bare `str`, accepting any junk
    # as a "username". It's now pydantic's EmailStr.
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': 'not-an-email'})  # noqa: E501
    assert response.status_code == 400
    assert response.json().get("success") is False


def test_singouins_auth_register_duplicate_does_not_leak_hash():
    # Registering the same user again hits the 409 "already exists" branch,
    # which had the exact same hash-leak bug on its own separate response.
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': USER_NAME})  # noqa: E501
    assert response.status_code == 409
    assert 'hash' not in response.json().get("user", {})


def test_singouins_auth_login():
    response = requests.post(f'{API_URL}/login', json=AUTH_PAYLOAD)
    assert response.status_code == 200
    assert response.json().get("access_token")
    assert response.json().get("refresh_token")


def test_singouins_auth_login_does_not_leak_username_existence():
    # Regression test: an unknown username used to return 404 "User not
    # found" while a wrong password on a real account returned 401 "Wrong
    # password" - letting a caller enumerate valid usernames by watching
    # which response they got. Both must now be identical.
    unknown_user_response = requests.post(
        f'{API_URL}/login',
        json={'username': 'does-not-exist@exemple.net', 'password': 'plop'},
        )
    wrong_password_response = requests.post(
        f'{API_URL}/login',
        json={'username': USER_NAME, 'password': 'not-the-right-password'},
        )

    assert unknown_user_response.status_code == 401
    assert wrong_password_response.status_code == 401
    assert unknown_user_response.json() == wrong_password_response.json()


def test_singouins_auth_infos(jwt_header):
    response  = requests.get(f'{API_URL}/infos', headers=jwt_header['access'])
    assert response.status_code == 200
    assert response.json().get("logged_in_as") == USER_NAME


def test_singouins_auth_refresh(jwt_header):
    response  = requests.post(f'{API_URL}/refresh', headers=jwt_header['refresh'])
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
    response = requests.post(f'{API_URL}/refresh', headers=jwt_header['refresh'])
    assert response.status_code == 200
    new_access_token = response.json().get("access_token")

    response = requests.get(
        f'{API_URL}/infos',
        headers={"Authorization": f"Bearer {new_access_token}"},
        )
    assert response.status_code == 200
    assert response.json().get("logged_in_as") == USER_NAME


def test_singouins_auth_refresh_token_is_revocable():
    # Regression test: a refreshed access token must go through the exact
    # same revocation path as a login-issued one.
    response = requests.post(f'{API_URL}/login', json=AUTH_PAYLOAD)
    refresh_header = {"Authorization": f"Bearer {response.json().get('refresh_token')}"}

    response = requests.post(f'{API_URL}/refresh', headers=refresh_header)
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}

    response = requests.delete(f'{API_URL}/logout', headers=access_header)
    assert response.status_code == 200
    assert 'JTI Revokation OK' in response.json().get("msg")

    response = requests.get(f'{API_URL}/infos', headers=access_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")


def test_singouins_auth_infos_rejects_missing_token():
    response = requests.get(f'{API_URL}/infos')
    assert response.status_code == 401


def test_singouins_auth_infos_rejects_garbage_token():
    response = requests.get(
        f'{API_URL}/infos',
        headers={"Authorization": "Bearer not-a-real-token"},
        )
    assert response.status_code in (401, 422)


def test_singouins_auth_logout():
    # We do a manual login (no from fixture) to avoid revoking global session token
    response = requests.post(f'{API_URL}/login', json=AUTH_PAYLOAD)
    access_token = response.json().get("access_token")
    access_header = {"Authorization": f"Bearer {access_token}"}

    # We check token revokation through logout
    response = requests.delete(f'{API_URL}/logout', headers=access_header)
    assert response.status_code == 200
    assert 'JTI Revokation OK' in response.json().get("msg")

    # We check token is revoked and access Unauthorized
    response  = requests.get(f'{API_URL}/infos', headers=access_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")


def test_singouins_auth_logout_also_revokes_refresh_token():
    # Regression test: logout used to only blocklist the access token,
    # leaving the refresh token (30-day life) usable to mint new access
    # tokens indefinitely after "logging out".
    response = requests.post(f'{API_URL}/login', json=AUTH_PAYLOAD)
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    refresh_header = {"Authorization": f"Bearer {response.json().get('refresh_token')}"}

    response = requests.delete(f'{API_URL}/logout', headers=access_header)
    assert response.status_code == 200
    assert 'JTI Revokation OK' in response.json().get("msg")

    response = requests.post(f'{API_URL}/refresh', headers=refresh_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")


def test_singouins_auth_confirm_happy_path():
    mail = 'confirm-happy@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    # The confirmation token is only ever emailed, never returned by the
    # API - fetch it the same way support tooling would, straight from the
    # Redis lookup key generate_confirmation_token() also writes.
    token = r.get(f"{API_ENV}:auth:current_confirm_token:{mail}")
    assert token is not None

    response = requests.get(f'{API_URL}/confirm/{token.decode()}')
    assert response.status_code == 200
    assert 'User confirmation OK' in response.json().get("msg")

    # Cleanup: log in as the throwaway user and delete it via /auth/delete.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'plop'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_confirm_unknown_user():
    # Regression test: a token resolving to an email with no matching User
    # document used to raise AttributeError (None.active = True), silently
    # survived only because it happened to land inside a broad except.
    # Write a token directly to Redis, the same way generate_confirmation_
    # token() does, for an email that was never registered.
    token = secrets.token_urlsafe(16)
    r.set(f"{API_ENV}:auth:confirm_token:{token}", "ghost@exemple.net", ex=60)

    response = requests.get(f'{API_URL}/confirm/{token}')
    assert response.status_code == 200
    assert 'user not found' in response.json().get("msg")


def test_singouins_auth_confirm_invalid_token():
    response = requests.get(f'{API_URL}/confirm/not-a-real-token')
    assert response.status_code == 200
    assert 'invalid or has expired' in response.json().get("msg")


def test_singouins_auth_resend_unknown_email_looks_identical_to_known():
    # Same enumeration-safety principle as login: an unknown email must
    # get back the exact same response as a real, unconfirmed one.
    mail = 'resend-target@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    known_response = requests.post(f'{API_URL}/resend', json={'mail': mail})
    unknown_response = requests.post(f'{API_URL}/resend', json={'mail': 'does-not-exist@exemple.net'})  # noqa: E501

    assert known_response.status_code == 200
    assert unknown_response.status_code == 200
    assert known_response.json() == unknown_response.json()

    # Cleanup.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'plop'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_resend_issues_a_working_token():
    mail = 'resend-works@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    # Let the original registration token get overwritten by a resend.
    response = requests.post(f'{API_URL}/resend', json={'mail': mail})
    assert response.status_code == 200

    token = r.get(f"{API_ENV}:auth:current_confirm_token:{mail}")
    assert token is not None

    response = requests.get(f'{API_URL}/confirm/{token.decode()}')
    assert response.status_code == 200
    assert 'User confirmation OK' in response.json().get("msg")

    # Cleanup.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'plop'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_resend_already_confirmed():
    mail = 'resend-already-active@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    token = r.get(f"{API_ENV}:auth:current_confirm_token:{mail}").decode()
    requests.get(f'{API_URL}/confirm/{token}')

    # Resending for an already-confirmed account must not error, and must
    # look identical to every other case (no "already confirmed" signal).
    response = requests.post(f'{API_URL}/resend', json={'mail': mail})
    assert response.status_code == 200

    # Cleanup.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'plop'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_forgot_password_unknown_email_looks_identical_to_known():
    # Same enumeration-safety principle as login/resend.
    mail = 'forgot-target@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'plop', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    known_response = requests.post(f'{API_URL}/forgot-password', json={'mail': mail})  # noqa: E501
    unknown_response = requests.post(f'{API_URL}/forgot-password', json={'mail': 'does-not-exist@exemple.net'})  # noqa: E501

    assert known_response.status_code == 200
    assert unknown_response.status_code == 200
    assert known_response.json() == unknown_response.json()

    # Cleanup.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'plop'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_reset_password_works():
    mail = 'reset-works@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'old-password', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    response = requests.post(f'{API_URL}/forgot-password', json={'mail': mail})
    assert response.status_code == 200

    token = r.get(f"{API_ENV}:auth:current_reset_token:{mail}")
    assert token is not None

    response = requests.post(f'{API_URL}/reset-password', json={'token': token.decode(), 'password': 'new-password'})  # noqa: E501
    assert response.status_code == 200
    assert 'Reset password OK' in response.json().get("msg")

    # Old password no longer works, new one does.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'old-password'})  # noqa: E501
    assert response.status_code == 401

    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'new-password'})  # noqa: E501
    assert response.status_code == 200

    # Cleanup.
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_reset_password_invalid_token():
    response = requests.post(f'{API_URL}/reset-password', json={'token': 'not-a-real-token', 'password': 'whatever'})  # noqa: E501
    assert response.status_code == 400
    assert 'invalid or has expired' in response.json().get("msg")


def test_singouins_auth_reset_password_is_single_use():
    # Regression-shaped test: a reset token must not be replayable, unlike
    # a confirmation token - reusing it after a successful reset must fail.
    mail = 'reset-single-use@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'old-password', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    requests.post(f'{API_URL}/forgot-password', json={'mail': mail})
    token = r.get(f"{API_ENV}:auth:current_reset_token:{mail}").decode()

    response = requests.post(f'{API_URL}/reset-password', json={'token': token, 'password': 'new-password'})  # noqa: E501
    assert response.status_code == 200

    response = requests.post(f'{API_URL}/reset-password', json={'token': token, 'password': 'another-password'})  # noqa: E501
    assert response.status_code == 400

    # Cleanup.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'new-password'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)


def test_singouins_auth_reset_password_revokes_refresh_token():
    mail = 'reset-revokes@exemple.net'
    response = requests.post(f'{API_URL}/register', json={'password': 'old-password', 'mail': mail})  # noqa: E501
    assert response.status_code in (200, 201)

    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'old-password'})  # noqa: E501
    refresh_header = {"Authorization": f"Bearer {response.json().get('refresh_token')}"}

    requests.post(f'{API_URL}/forgot-password', json={'mail': mail})
    token = r.get(f"{API_ENV}:auth:current_reset_token:{mail}").decode()
    response = requests.post(f'{API_URL}/reset-password', json={'token': token, 'password': 'new-password'})  # noqa: E501
    assert response.status_code == 200

    # The refresh token issued before the reset must no longer work.
    response = requests.post(f'{API_URL}/refresh', headers=refresh_header)
    assert response.status_code == 401
    assert 'revoked' in response.json().get("msg")

    # Cleanup.
    response = requests.post(f'{API_URL}/login', json={'username': mail, 'password': 'new-password'})  # noqa: E501
    access_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    requests.delete(f'{API_URL}/delete', headers=access_header)
