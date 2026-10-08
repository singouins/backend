# -*- coding: utf8 -*-

import os
import sys

import pytest
from flask import Flask, jsonify

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# The /internal/* routes are service-to-service (fight resolver -> api),
# guarded by a shared token rather than a JWT. This checks the guard alone,
# with a minimal Flask app and no Mongo/Redis.

TOKEN = 'unit-test-token'


@pytest.fixture
def client(monkeypatch):
    """
    routes._decorators.internal reads `variables.SEP_INTERNAL_TOKEN` at call
    time. Inside api/tests that name resolves to tests/variables.py (loaded by
    conftest), not api/variables.py (which connects to Mongo at import), so
    the attribute is set there for the duration of the test.
    """
    monkeypatch.setattr(sys.modules['variables'], 'SEP_INTERNAL_TOKEN', TOKEN, raising=False)

    from routes._decorators import internal

    app = Flask(__name__)
    calls = []

    @app.route('/guarded', methods=['POST'])
    @internal.token
    def guarded():
        calls.append(1)
        return jsonify({"success": True, "msg": 'ran', "payload": None}), 200

    return app.test_client(), calls


def _post(client, headers=None):
    return client.post('/guarded', headers=headers or {})


def test_internal_token_unset_is_503(client, monkeypatch):
    client, calls = client
    monkeypatch.setattr(sys.modules['variables'], 'SEP_INTERNAL_TOKEN', None, raising=False)

    response = _post(client, {"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503
    assert response.json == {
        "success": False,
        "msg": 'Internal API disabled (no token configured)',
        "payload": None,
        }
    assert calls == []


def test_internal_token_empty_is_503(client, monkeypatch):
    client, calls = client
    monkeypatch.setattr(sys.modules['variables'], 'SEP_INTERNAL_TOKEN', '', raising=False)

    response = _post(client, {"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503
    assert calls == []


def test_internal_token_missing_header_is_401(client):
    client, calls = client

    response = _post(client)
    assert response.status_code == 401
    assert response.json['success'] is False
    assert response.json['payload'] is None
    assert calls == []


def test_internal_token_wrong_scheme_is_401(client):
    client, calls = client

    response = _post(client, {"Authorization": "Basic xxx"})
    assert response.status_code == 401
    assert calls == []


def test_internal_token_empty_bearer_is_401(client):
    client, calls = client

    response = _post(client, {"Authorization": "Bearer "})
    assert response.status_code == 401
    assert calls == []

    response = _post(client, {"Authorization": "Bearer"})
    assert response.status_code == 401
    assert calls == []


def test_internal_token_wrong_is_403(client):
    client, calls = client

    response = _post(client, {"Authorization": "Bearer not-the-token"})
    assert response.status_code == 403
    assert response.json['success'] is False
    assert TOKEN not in response.json['msg']
    assert calls == []


def test_internal_token_non_ascii_is_403(client):
    client, calls = client

    # Werkzeug decodes headers as latin-1, so a non-ASCII token reaches the
    # guard as str: it must be a plain 403, not a TypeError from compare_digest
    response = _post(client, {"Authorization": "Bearer tokén"})
    assert response.status_code == 403
    assert response.json['success'] is False
    assert calls == []


def test_internal_token_right_runs_the_view(client):
    client, calls = client

    response = _post(client, {"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    assert response.json['msg'] == 'ran'
    assert calls == [1]
