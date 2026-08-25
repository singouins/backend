# -*- coding: utf8 -*-

import json
import os
import time
import uuid

import redis
from websockets.sync.client import connect

# Redis variables
REDIS_HOST = os.environ.get("REDIS_HOST", '127.0.0.1')
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_BASE = int(os.environ.get("REDIS_BASE", 0))
# APP variables
API_ENV = os.environ.get("API_ENV", None)
# WebSocket variables
WSS_HOST = os.environ.get("WSS_HOST", '0.0.0.0')
WSS_PORT = int(os.environ.get("WSS_PORT", 5000))
WS_URL = f"ws://{'127.0.0.1' if WSS_HOST == '0.0.0.0' else WSS_HOST}:{WSS_PORT}"

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_BASE)

# Real keys are shaped {env}:{instance}:{type}:{creature}:{name}, e.g. as
# written by api/routes/mypc/action/profession/tracking.py.


def test_set_event_fields_match_key_layout():
    instance = str(uuid.uuid4())
    creature = str(uuid.uuid4())
    key = f'{API_ENV}:{instance}:effects:{creature}:SomeBuff'

    with connect(WS_URL, additional_headers={"X-Real-IP": "127.0.0.1"}) as ws:
        time.sleep(1)
        r.set(key, 'whatever')

        received = json.loads(ws.recv(timeout=5))
        assert received['event'] == 'set'
        assert received['key'] == key
        assert received['type'] == 'effects'
        assert received['creature'] == creature
        assert received['name'] == 'SomeBuff'


def test_expired_event_fields_match_key_layout():
    instance = str(uuid.uuid4())
    creature = str(uuid.uuid4())
    key = f'{API_ENV}:{instance}:effects:{creature}:SomeBuff'

    with connect(WS_URL, additional_headers={"X-Real-IP": "127.0.0.1"}) as ws:
        time.sleep(1)
        r.set(key, 'whatever', ex=1)

        # The "set" event fires immediately; "expired" follows once the TTL
        # elapses.
        set_event = json.loads(ws.recv(timeout=5))
        assert set_event['event'] == 'set'

        expired_event = json.loads(ws.recv(timeout=5))
        assert expired_event['event'] == 'expired'
        assert expired_event['key'] == key
        assert expired_event['type'] == 'effects'
        assert expired_event['creature'] == creature
        assert expired_event['name'] == 'SomeBuff'


def test_malformed_key_does_not_crash_the_listener():
    # A key that matches the API_ENV prefix but doesn't have the full
    # {instance}:{type}:{creature}:{name} shape must not crash the listener
    # (see the IndexError guard added alongside the key-layout fix) - it
    # should be silently skipped, and a well-formed key right after it
    # should still be relayed normally.
    malformed_key = f'{API_ENV}:tooshort'
    well_formed_key = f'{API_ENV}:{uuid.uuid4()}:effects:{uuid.uuid4()}:Buff'

    with connect(WS_URL, additional_headers={"X-Real-IP": "127.0.0.1"}) as ws:
        time.sleep(1)
        r.set(malformed_key, 'whatever')
        r.set(well_formed_key, 'whatever')

        received = json.loads(ws.recv(timeout=5))
        assert received['key'] == well_formed_key
