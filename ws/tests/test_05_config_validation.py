# -*- coding: utf8 -*-

import os
import subprocess
import sys

MAIN_PY = os.path.join(os.path.dirname(__file__), '..', 'main.py')


def _run_main(env):
    # main.py validates API_ENV before touching Redis or opening a socket,
    # so this exits almost instantly - no Redis/network dependency needed.
    return subprocess.run(
        [sys.executable, MAIN_PY],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_missing_api_env_fails_fast():
    env = os.environ.copy()
    env.pop('API_ENV', None)
    result = _run_main(env)

    assert result.returncode != 0
    assert 'API_ENV' in result.stderr
    # A controlled sys.exit(), not an unhandled AttributeError/TypeError
    # traceback from the old eager-evaluated f-string default.
    assert 'Traceback' not in result.stderr


def test_empty_api_env_fails_fast():
    env = os.environ.copy()
    env['API_ENV'] = ''
    result = _run_main(env)

    assert result.returncode != 0
    assert 'API_ENV' in result.stderr
    assert 'Traceback' not in result.stderr
