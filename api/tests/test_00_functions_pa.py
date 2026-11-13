# -*- coding: utf8 -*-

import fakeredis
import pytest
import redis

from redis_functions import (
    FUNCTIONS_PA_FILE,
    FUNCTIONS_PA_HELM_BLOB,
    FUNCTIONS_PA_HELM_COMMIT,
    FUNCTIONS_PA_HELM_PATH,
    FUNCTIONS_PA_VERSION,
    functions_pa_blob,
    load_functions_pa,
    )


def test_functions_pa_copy_is_the_helm_file():
    """
    fixtures/functions_pa.lua is byte-identical to helm's file at
    FUNCTIONS_PA_HELM_COMMIT: an edit to the copy fails here, so the
    copy cannot drift silently from the source of truth.
    """
    assert functions_pa_blob() == FUNCTIONS_PA_HELM_BLOB, (
        f'{FUNCTIONS_PA_FILE} differs from singouins/helm {FUNCTIONS_PA_HELM_PATH}'
        f' at {FUNCTIONS_PA_HELM_COMMIT}')


def test_functions_pa_version():
    client = fakeredis.FakeStrictRedis(server=fakeredis.FakeServer())
    load_functions_pa(client)

    assert client.fcall('pa_version', 0) == FUNCTIONS_PA_VERSION


def test_functions_pa_version_on_real_redis():
    """
    The CI Redis service: the workflow loads the library before starting the
    apps (the databases chart does it in production). The API needs VERSION 3.
    """
    from variables import r as client
    try:
        client.ping()
    except redis.exceptions.RedisError:
        pytest.skip('no Redis server reachable')
    load_functions_pa(client)

    assert client.fcall('pa_version', 0) == FUNCTIONS_PA_VERSION
