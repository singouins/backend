# -*- coding: utf8 -*-

import os
import sys
import threading
import time
import uuid

import fakeredis
import pytest
import redis

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

from utils.pa import (  # noqa: E402
    BLUE_PA_MAX,
    RED_PA_MAX,
    pa_cost_split,
    pa_durations,
    pa_from_ttl,
    ttl_after_spend,
    )

# Issue #498: try_consume_pa() checks and spends in one atomic step, refund_pa()
# gives PA back. Unit tests against fakeredis, plus the concurrency test
# against the real Redis of the CI when it is reachable.
TICK = 3600
DURATIONS = pa_durations(TICK)
ROUNDS = 25
# Delay before each Redis command: widens the window between a read and a
# write, so a non-atomic check-then-spend lets both racers through
COMMAND_DELAY = 0.005


def _env(monkeypatch):
    """
    utils.redis imports `variables` for env_vars. Inside api/tests that name
    resolves to tests/variables.py (loaded by conftest), not api/variables.py
    (which connects to Mongo at import), so env_vars is provided here.
    """
    # Same keys as api/variables.py: utils.redis builds its (lazy) pool from them at import
    env_vars = {
        'API_ENV': 'pytest',
        'REDIS_HOST': '127.0.0.1',
        'REDIS_PORT': 6379,
        'REDIS_BASE': 0,
        }
    monkeypatch.setattr(sys.modules['variables'], 'env_vars', env_vars, raising=False)

    import utils.redis as utils_redis
    return utils_redis


@pytest.fixture
def pa_redis(monkeypatch):
    """ utils.redis on an in-memory fakeredis. """
    utils_redis = _env(monkeypatch)
    monkeypatch.setattr(utils_redis, 'r', fakeredis.FakeStrictRedis(server=fakeredis.FakeServer()))
    return utils_redis


@pytest.fixture
def real_redis(monkeypatch):
    """ utils.redis on the real Redis (CI service), skipped when it is not reachable. """
    from variables import r as client
    try:
        client.ping()
    except redis.exceptions.RedisError:
        pytest.skip('no Redis server reachable')
    utils_redis = _env(monkeypatch)
    monkeypatch.setattr(utils_redis, 'r', client)
    created = []
    yield utils_redis, created
    for creatureuuid in created:
        client.delete(*_keys(utils_redis, creatureuuid).values())


@pytest.fixture
def slow_commands(monkeypatch):
    """ Every Redis command (fakeredis or real, client or pipeline) waits COMMAND_DELAY first. """
    send = redis.connection.AbstractConnection.send_packed_command

    def delayed(self, *args, **kwargs):
        time.sleep(COMMAND_DELAY)
        return send(self, *args, **kwargs)

    monkeypatch.setattr(redis.connection.AbstractConnection, 'send_packed_command', delayed)


def _keys(utils_redis, creatureuuid):
    return {
        'blue': f"{utils_redis.env_vars['API_ENV']}:pas:{creatureuuid}:blue",
        'red': f"{utils_redis.env_vars['API_ENV']}:pas:{creatureuuid}:red",
        }


def _pa(utils_redis, creatureuuid):
    """ PA available now, by colour. """
    pa = utils_redis.get_pa(creatureuuid=creatureuuid, tick=TICK)
    return {colour: pa[colour]['pa'] for colour in ('red', 'blue')}


def _set_pa(utils_redis, creatureuuid, red, blue):
    """ Sets both pools to exactly that many PA (whole PA, no partial regeneration). """
    for colour, pa, pa_max in (('red', red, 16), ('blue', blue, 8)):
        key = _keys(utils_redis, creatureuuid)[colour]
        missing = pa_max - pa
        if missing > 0:
            utils_redis.r.set(key, 'None', ex=missing * DURATIONS[colour])
        else:
            utils_redis.r.delete(key)


def _creature():
    return str(uuid.uuid4())


#
# try_consume_pa()
#
def test_try_consume_pa_affordable_spends(pa_redis):
    creatureuuid = _creature()

    assert pa_redis.try_consume_pa(creatureuuid, redpa=1, bluepa=2, tick=TICK) is True

    assert _pa(pa_redis, creatureuuid) == {'red': 15, 'blue': 6}


def test_try_consume_pa_spends_like_consume_pa(pa_redis):
    """ Same TTLs as the non-atomic consume_pa() for the same costs. """
    atomic, legacy = _creature(), _creature()

    pa_redis.try_consume_pa(atomic, redpa=3, bluepa=5, tick=TICK)
    pa_redis.consume_pa(legacy, redpa=3, bluepa=5, tick=TICK)

    assert _pa(pa_redis, atomic) == _pa(pa_redis, legacy)


def test_try_consume_pa_red_covers_blue_shortfall(pa_redis):
    """ Q104: 2 blue left, the action costs 1 red + 3 blue: 2 blue + 2 red are spent. """
    creatureuuid = _creature()
    _set_pa(pa_redis, creatureuuid, red=10, blue=2)

    assert pa_redis.try_consume_pa(creatureuuid, redpa=1, bluepa=3, tick=TICK) is True

    assert _pa(pa_redis, creatureuuid) == {'red': 8, 'blue': 0}


def test_try_consume_pa_exact_boundary(pa_redis):
    creatureuuid = _creature()
    _set_pa(pa_redis, creatureuuid, red=3, blue=0)

    assert pa_redis.try_consume_pa(creatureuuid, redpa=1, bluepa=2, tick=TICK) is True

    assert _pa(pa_redis, creatureuuid) == {'red': 0, 'blue': 0}


@pytest.mark.parametrize('redpa, bluepa', [(4, 0), (2, 3), (0, 5)])
def test_try_consume_pa_unaffordable_spends_nothing(pa_redis, redpa, bluepa):
    creatureuuid = _creature()
    _set_pa(pa_redis, creatureuuid, red=3, blue=1)
    before = {key: pa_redis.r.ttl(key) for key in _keys(pa_redis, creatureuuid).values()}

    assert pa_redis.try_consume_pa(creatureuuid, redpa=redpa, bluepa=bluepa, tick=TICK) is False

    after = {key: pa_redis.r.ttl(key) for key in _keys(pa_redis, creatureuuid).values()}
    assert after == before


def test_try_consume_pa_zero_cost_writes_nothing(pa_redis):
    creatureuuid = _creature()

    assert pa_redis.try_consume_pa(creatureuuid, tick=TICK) is True

    assert not pa_redis.r.exists(*_keys(pa_redis, creatureuuid).values())


def test_try_consume_pa_outside_instance(pa_redis, monkeypatch):
    """ No Instance, no PA: True and Redis is never called. """
    monkeypatch.setattr(pa_redis, 'r', None)

    assert pa_redis.try_consume_pa(_creature(), redpa=99, bluepa=99, tick=None) is True


def test_try_consume_pa_tick_is_keyword_only_and_mandatory(pa_redis):
    with pytest.raises(TypeError):
        pa_redis.try_consume_pa(_creature(), 0, 1, TICK)
    with pytest.raises(TypeError):
        pa_redis.try_consume_pa(_creature(), bluepa=1)


#
# refund_pa()
#
def test_refund_pa_gives_back_what_was_spent(pa_redis):
    creatureuuid = _creature()
    _set_pa(pa_redis, creatureuuid, red=10, blue=5)
    pa_redis.try_consume_pa(creatureuuid, redpa=2, bluepa=3, tick=TICK)

    pa_redis.refund_pa(creatureuuid, redpa=2, bluepa=3, tick=TICK)

    assert _pa(pa_redis, creatureuuid) == {'red': 10, 'blue': 5}


def test_refund_pa_back_to_full_deletes_the_key(pa_redis):
    creatureuuid = _creature()
    pa_redis.try_consume_pa(creatureuuid, redpa=2, bluepa=1, tick=TICK)

    pa_redis.refund_pa(creatureuuid, redpa=2, bluepa=1, tick=TICK)

    assert not pa_redis.r.exists(*_keys(pa_redis, creatureuuid).values())
    assert _pa(pa_redis, creatureuuid) == {'red': 16, 'blue': 8}


def test_refund_pa_never_goes_above_full(pa_redis):
    creatureuuid = _creature()
    _set_pa(pa_redis, creatureuuid, red=15, blue=8)

    pa_redis.refund_pa(creatureuuid, redpa=5, bluepa=5, tick=TICK)

    assert not pa_redis.r.exists(*_keys(pa_redis, creatureuuid).values())
    assert _pa(pa_redis, creatureuuid) == {'red': 16, 'blue': 8}


def test_refund_pa_red_covered_part_is_refunded_as_red(pa_redis):
    """ Q104: 1 blue left, 2 blue spent as 1 blue + 1 red: the refund is per pool. """
    creatureuuid = _creature()
    _set_pa(pa_redis, creatureuuid, red=10, blue=1)
    pa_redis.try_consume_pa(creatureuuid, bluepa=2, tick=TICK)

    pa_redis.refund_pa(creatureuuid, redpa=1, bluepa=1, tick=TICK)

    assert _pa(pa_redis, creatureuuid) == {'red': 10, 'blue': 1}


def test_refund_pa_outside_instance(pa_redis, monkeypatch):
    monkeypatch.setattr(pa_redis, 'r', None)

    assert pa_redis.refund_pa(_creature(), redpa=1, bluepa=1, tick=None) is None


#
# Concurrency: two simultaneous consumes, only one affordable
#
def _race(utils_redis, creatureuuid, redpa, bluepa):
    """ Starts two try_consume_pa() together, returns both results. """
    barrier = threading.Barrier(2)
    results = []

    def consume():
        barrier.wait()
        results.append(utils_redis.try_consume_pa(
            creatureuuid, redpa=redpa, bluepa=bluepa, tick=TICK))

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(results)


@pytest.mark.parametrize('redpa, bluepa, left', [
    # 10 red twice is 20 > 16
    (10, 0, {'red': 6, 'blue': 8}),
    # The first takes the 8 blue + 5 red, the second needs 5 + 8 red > 11
    (5, 8, {'red': 11, 'blue': 0}),
    ])
def test_concurrent_consumes_only_one_passes(pa_redis, slow_commands, redpa, bluepa, left):
    for _ in range(ROUNDS):
        creatureuuid = _creature()

        assert _race(pa_redis, creatureuuid, redpa, bluepa) == [False, True]
        assert _pa(pa_redis, creatureuuid) == left


def test_concurrent_consumes_only_one_passes_on_real_redis(real_redis, slow_commands):
    utils_redis, created = real_redis
    for _ in range(ROUNDS):
        creatureuuid = _creature()
        created.append(creatureuuid)

        assert _race(utils_redis, creatureuuid, 10, 0) == [False, True]
        assert _pa(utils_redis, creatureuuid) == {'red': 6, 'blue': 8}


def test_consume_and_refund_on_real_redis(real_redis):
    utils_redis, created = real_redis
    creatureuuid = _creature()
    created.append(creatureuuid)

    assert utils_redis.try_consume_pa(creatureuuid, redpa=1, bluepa=9, tick=TICK) is True
    assert _pa(utils_redis, creatureuuid) == {'red': 14, 'blue': 0}
    assert utils_redis.try_consume_pa(creatureuuid, redpa=15, tick=TICK) is False

    utils_redis.refund_pa(creatureuuid, redpa=2, bluepa=8, tick=TICK)
    assert _pa(utils_redis, creatureuuid) == {'red': 16, 'blue': 8}


def test_partial_pools_consume_and_refund_on_real_redis(real_redis):
    """ Existing keys: the spend and the refund move their TTL (EXPIRE), never SET or DEL. """
    utils_redis, created = real_redis
    creatureuuid = _creature()
    created.append(creatureuuid)
    _set_pa(utils_redis, creatureuuid, red=10, blue=5)

    assert utils_redis.try_consume_pa(creatureuuid, redpa=2, bluepa=3, tick=TICK) is True
    assert _pa(utils_redis, creatureuuid) == {'red': 8, 'blue': 2}

    utils_redis.refund_pa(creatureuuid, redpa=1, bluepa=2, tick=TICK)
    assert _pa(utils_redis, creatureuuid) == {'red': 9, 'blue': 4}


#
# Lua: the script duplicates utils.pa (Q104 split, TTL arithmetic), checked on a grid
#
class _RecordingRedis:
    """ The `redis` table the script sees: TTL from a dict, writes recorded. """

    def __init__(self, ttls):
        self.ttls = ttls
        self.writes = []

    def call(self, command, key, *args):
        if command == 'TTL':
            return self.ttls[key]
        # Redis needs whole numbers: a fractional TTL would be refused there
        for arg in args:
            assert isinstance(arg, str) or float(arg).is_integer(), (command, key, args)
        self.writes.append((command, key) + tuple(arg if isinstance(arg, str) else int(arg)
                                                  for arg in args))


def _python_reference(ttls, red_cost, blue_cost, durations):
    """ What utils.pa says the script must do: (result, writes). """
    pa_max = {'blue': BLUE_PA_MAX, 'red': RED_PA_MAX}
    available = {colour: pa_from_ttl(ttls[colour], pa_max[colour], durations[colour])['pa']
                 for colour in ('blue', 'red')}
    split = pa_cost_split(available['red'], available['blue'], red_cost, blue_cost)
    if split is None:
        return 0, []
    writes = []
    for colour in ('blue', 'red'):
        if split[colour] > 0:
            new_ttl = ttl_after_spend(ttls[colour], split[colour], durations[colour])
            if ttls[colour] > 0:
                writes.append(('EXPIRE', colour, new_ttl))
            else:
                writes.append(('SET', colour, 'None', 'EX', new_ttl))
    return 1, writes


def _ttl_grid(pa_max, duration):
    """ Absent, no expiry, then around every half PA up to past the max. """
    ttls = {-2, -1}
    for half in range(0, 2 * pa_max + 3):
        for delta in (-1, 0, 1):
            ttl = half * duration // 2 + delta
            if ttl > 0:
                ttls.add(ttl)
    return sorted(ttls)


@pytest.mark.parametrize('tick', [60, 3600])
def test_lua_matches_python_q104_and_ttl_arithmetic(pa_redis, tick):
    from lupa.lua51 import LuaRuntime

    durations = pa_durations(tick)
    lua = LuaRuntime()
    script = lua.eval('function() ' + pa_redis.TRY_CONSUME_PA_LUA + ' end')
    lua_globals = lua.globals()
    lua_globals.KEYS = lua.table('blue', 'red')
    checked = 0
    for blue_ttl in _ttl_grid(BLUE_PA_MAX, durations['blue']):
        for red_ttl in _ttl_grid(RED_PA_MAX, durations['red']):
            ttls = {'blue': blue_ttl, 'red': red_ttl}
            for red_cost in (0, 1, 5, 16):
                for blue_cost in (0, 1, 3, 8, 9):
                    stub = _RecordingRedis(ttls)
                    lua_globals.redis = stub
                    # Strings, as Redis passes ARGV
                    lua_globals.ARGV = lua.table(*map(str, (
                        red_cost, blue_cost, durations['red'], durations['blue'],
                        RED_PA_MAX, BLUE_PA_MAX,
                        )))
                    result = int(script())
                    expected = _python_reference(ttls, red_cost, blue_cost, durations)
                    assert (result, stub.writes) == expected, (ttls, red_cost, blue_cost)
                    checked += 1
    assert checked > 10000
