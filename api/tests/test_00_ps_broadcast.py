# -*- coding: utf8 -*-

import importlib.util
import os
import sys
import types

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# PS_BROADCAST is the pubsub channel the ws service relays to the clients.
# ws/main.py subscribes to ws-broadcast-<env> by default (ruling 2026-11-04:
# ws-broadcast-dev on dev, ws-broadcast-prod on prod): the API default must
# follow the same rule. The routes using it are covered in
# test_00_equip_params.py. Pure unit test: no Mongo, no Redis.


def _load_api_variables(monkeypatch):
    """
    Executes the real api/variables.py under a private name. Its only Mongo
    use is the metas, stubbed with one each (none would stop it at import);
    nothing is left in sys.modules.
    """
    stub = types.SimpleNamespace(
        to_mongo=lambda: types.SimpleNamespace(to_dict=lambda: {'_id': 1}),
        )
    meta = types.ModuleType('mongo.models.Meta')
    for name in ('MetaArmor', 'MetaRace', 'MetaRecipe', 'MetaWeapon'):
        setattr(meta, name, types.SimpleNamespace(objects=lambda: [stub]))
    monkeypatch.setitem(sys.modules, 'mongo.models.Meta', meta)
    monkeypatch.setenv('SEP_SECRET_KEY', 'unit-test-secret')

    path = os.path.join(LOCAL_PATH, 'variables.py')
    spec = importlib.util.spec_from_file_location('_api_variables_ps_broadcast', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ps_broadcast_follows_api_env(monkeypatch):
    monkeypatch.delenv('PS_BROADCAST', raising=False)
    monkeypatch.setenv('API_ENV', 'DEV')
    assert _load_api_variables(monkeypatch).PS_BROADCAST == 'ws-broadcast-dev'

    monkeypatch.setenv('API_ENV', 'PROD')
    assert _load_api_variables(monkeypatch).PS_BROADCAST == 'ws-broadcast-prod'


def test_ps_broadcast_env_override_wins(monkeypatch):
    monkeypatch.setenv('API_ENV', 'DEV')
    monkeypatch.setenv('PS_BROADCAST', 'custom-channel')
    assert _load_api_variables(monkeypatch).PS_BROADCAST == 'custom-channel'


def test_ps_broadcast_without_api_env_does_not_crash(monkeypatch):
    monkeypatch.delenv('PS_BROADCAST', raising=False)
    monkeypatch.delenv('API_ENV', raising=False)
    assert _load_api_variables(monkeypatch).PS_BROADCAST == 'ws-broadcast-none'
