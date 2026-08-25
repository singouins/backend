# -*- coding: utf8 -*-

import os
import signal
import subprocess
import sys
import time

import websockets.exceptions
from websockets.sync.client import connect

MAIN_PY = os.path.join(os.path.dirname(__file__), '..', 'main.py')
# A dedicated port so this test's own main.py subprocess doesn't collide
# with the instance CI already has running in the background for the rest
# of the suite.
TEST_PORT = 5099


def test_sigterm_closes_clients_cleanly_and_exits_promptly():
    env = os.environ.copy()
    env['WSS_PORT'] = str(TEST_PORT)
    proc = subprocess.Popen([sys.executable, MAIN_PY], env=env)

    ws = None
    try:
        # Wait for the server to actually be listening.
        for _ in range(50):
            try:
                ws = connect(
                    f'ws://127.0.0.1:{TEST_PORT}',
                    additional_headers={"X-Real-IP": "127.0.0.1"},
                    )
                break
            except OSError:
                time.sleep(0.2)
        assert ws is not None, "server never became reachable"

        start = time.monotonic()
        proc.send_signal(signal.SIGTERM)

        # A graceful shutdown sends a clean close frame (not just resetting
        # the TCP connection), and it does so promptly - it must not need
        # docker's SIGKILL-after-grace-period fallback to actually exit.
        try:
            ws.recv(timeout=10)
            raise AssertionError("expected the connection to be closed")
        except websockets.exceptions.ConnectionClosedOK as e:
            assert e.rcvd.code == 1001  # going away
        elapsed = time.monotonic() - start
        assert elapsed < 5

        proc.wait(timeout=5)
        assert proc.returncode == 0
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
