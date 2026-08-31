# -*- coding: utf8 -*-

import requests

from variables import API_URL, AUTH_PAYLOAD, USER_NAME


def test_singouins_pc_delete(jwt_header, mypc):
    if mypc['raw'] and len(mypc['raw']) > 0:
        for pc in mypc['raw']:
            if 'instance' in pc:
                # We need to leave the instance
                response = requests.post(f"{API_URL}/mypc/{pc['_id']}/instance/{pc['instance']}/leave", headers=jwt_header['access'])  # noqa: E501
                assert response.status_code == 200
                assert response.json().get("success") is True

            # We delete the PC
            response = requests.delete(f"{API_URL}/mypc/{pc['_id']}", headers=jwt_header['access'])
            assert response.status_code == 200
            assert response.json().get("success") is True


def test_singouins_auth_delete_ignores_spoofed_username():
    # Regression test: DELETE /auth/delete must always target the caller's
    # own account. It used to trust a `username` field in the request body
    # with no ownership check, letting any authenticated user delete anyone
    # else's account (IDOR). Uses a disposable second account so the shared
    # session user (USER_NAME) is left untouched for the real cleanup below.
    attacker_name = 'idor-attacker@exemple.net'
    response = requests.post(f'{API_URL}/auth/register', json={'password': 'plop', 'mail': attacker_name})  # noqa: E501
    assert response.status_code in (200, 201, 409)

    response = requests.post(f'{API_URL}/auth/login', json={'username': attacker_name, 'password': 'plop'})  # noqa: E501
    assert response.status_code == 200
    attacker_header = {"Authorization": f"Bearer {response.json().get('access_token')}"}

    # Attacker tries to delete the victim (the shared test user) by naming
    # them in the body - this should only ever delete the attacker.
    response = requests.delete(f'{API_URL}/auth/delete', json={'username': USER_NAME}, headers=attacker_header)  # noqa: E501
    assert response.status_code == 200
    assert 'User deletion OK' in response.json().get("msg")

    # The victim must still be able to log in - they were never touched.
    response = requests.post(f'{API_URL}/auth/login', json=AUTH_PAYLOAD)
    assert response.status_code == 200
    assert response.json().get("access_token")


def test_singouins_auth_delete(jwt_header):
    response = requests.delete(f'{API_URL}/auth/delete', headers=jwt_header['access'])
    assert response.status_code == 200
    assert 'User deletion OK' in response.json().get("msg")
