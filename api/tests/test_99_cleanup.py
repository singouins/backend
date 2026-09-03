# -*- coding: utf8 -*-

import requests

from variables import API_URL, AUTH_API_URL


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


def test_singouins_auth_delete(jwt_header):
    # Deletes the shared test account via the auth service - the account
    # itself, and the IDOR regression test for this same route, live in
    # auth/tests/ now (see auth/tests/test_99_cleanup.py).
    response = requests.delete(f'{AUTH_API_URL}/delete', headers=jwt_header['access'])
    assert response.status_code == 200
    assert 'User deletion OK' in response.json().get("msg")
