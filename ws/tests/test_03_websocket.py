# -*- coding: utf8 -*-

import json
import os
import time

import redis
from websockets.sync.client import connect

# Redis variables
REDIS_HOST = os.environ.get("REDIS_HOST", '127.0.0.1')
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_BASE = int(os.environ.get("REDIS_BASE", 0))
# APP variables
API_ENV = os.environ.get("API_ENV", None)
# PubSub variables
PS_BROADCAST = os.environ.get("PS_BROADCAST", f'ws-broadcast-{API_ENV.lower()}')
# WebSocket variables
WSS_HOST = os.environ.get("WSS_HOST", '0.0.0.0')
WSS_PORT = int(os.environ.get("WSS_PORT", 5000))
WS_URL = f"ws://{'127.0.0.1' if WSS_HOST == '0.0.0.0' else WSS_HOST}:{WSS_PORT}"

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_BASE)


def test_connect():
    # The handshake itself succeeds even when websocket_handler() has a bad
    # signature/attribute access, since the crash only happens once the
    # server invokes the handler after the handshake completes. So give the
    # server time to run (and crash) the handler before checking the
    # connection is still alive.
    with connect(WS_URL, additional_headers={"X-Real-IP": "127.0.0.1"}) as ws:
        time.sleep(1)
        assert ws.state.name == "OPEN"


def test_broadcast_relay():
    payload = {"hello": "world"}

    with connect(WS_URL, additional_headers={"X-Real-IP": "127.0.0.1"}) as ws:
        # Give the server's Redis subscriber time to attach before publishing
        time.sleep(1)
        r.publish(PS_BROADCAST, json.dumps(payload))

        received = ws.recv(timeout=5)
        assert json.loads(received) == payload
