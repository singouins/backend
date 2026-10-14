# -*- coding: utf8 -*-

import os
import sys

from unittest.mock import MagicMock

import fakeredis
import pytest

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
    pa_shortfall_colour,
    pa_spend_split,
    ttl_after_spend,
    )

CREATURE_ID = '00000000-0000-0000-0000-00000000c0fe'


#
# Pure arithmetic (no service needed)
#
def test_pa_constants():
    assert RED_PA_MAX == 16
    assert BLUE_PA_MAX == 8


def test_pa_durations_normal_tick():
    """ Red regenerates 1 PA per tick, blue 1 PA per 2 ticks. """
    assert pa_durations(3600) == {'red': 3600, 'blue': 7200}


def test_pa_durations_fast_tick():
    assert pa_durations(60) == {'red': 60, 'blue': 120}


@pytest.mark.parametrize('ttl', [-2, -1])
def test_pa_from_ttl_pool_full(ttl):
    """ A missing key (ttl -2) or a key without expiry (ttl -1) is a full pool. """
    assert pa_from_ttl(ttl, RED_PA_MAX, 3600) == {'pa': 16, 'ttnpa': 0, 'ttl': ttl}
    assert pa_from_ttl(ttl, BLUE_PA_MAX, 7200) == {'pa': 8, 'ttnpa': 0, 'ttl': ttl}


def test_pa_from_ttl_blue_two_spent_normal_tick():
    """
    PO example: blue pool, 2 PA just spent in a normal instance (TTL 14400).
    With the blue duration of 2 ticks that is 6 PA left, not 4.
    """
    assert pa_from_ttl(14400, BLUE_PA_MAX, 7200) == {'pa': 6, 'ttnpa': 0, 'ttl': 14400}


def test_pa_from_ttl_red_partially_regenerated():
    """ 5000s left on a red pool: 1 PA still missing, 1400s before the next one. """
    assert pa_from_ttl(5000, RED_PA_MAX, 3600) == {'pa': 15, 'ttnpa': 1400, 'ttl': 5000}


def test_pa_from_ttl_fast_instance():
    """ Fast instance (tick 60): 3 red PA spent 10s ago. """
    assert pa_from_ttl(170, RED_PA_MAX, 60) == {'pa': 13, 'ttnpa': 50, 'ttl': 170}
    # Same instance, 1 blue PA spent 30s ago (blue duration 120s)
    assert pa_from_ttl(90, BLUE_PA_MAX, 120) == {'pa': 7, 'ttnpa': 90, 'ttl': 90}


def test_ttl_after_spend_from_absent_key():
    """ Spending on a full pool starts the TTL from zero, not from Redis' -2. """
    assert ttl_after_spend(-2, 2, 7200) == 14400
    assert ttl_after_spend(-1, 1, 3600) == 3600


def test_ttl_after_spend_from_existing_ttl():
    assert ttl_after_spend(5000, 1, 3600) == 8600
    assert ttl_after_spend(170, 2, 60) == 290


#
# Red covers blue (designer ruling Q104, pure)
#
def test_pa_cost_split_enough_blue_uses_no_red():
    assert pa_cost_split(16, 8, 0, 2) == {'red': 0, 'blue': 2}
    assert pa_cost_split(16, 8, 1, 2) == {'red': 1, 'blue': 2}


def test_pa_cost_split_shortfall_covered_by_red():
    """ 1 blue left for a 3 blue action: 2 red cover the shortfall. """
    assert pa_cost_split(16, 1, 0, 3) == {'red': 2, 'blue': 1}


def test_pa_cost_split_shortfall_added_to_own_red_cost():
    """ 2 red + 3 blue action with 1 blue left: 2 + 2 red, 1 blue. """
    assert pa_cost_split(16, 1, 2, 3) == {'red': 4, 'blue': 1}


def test_pa_cost_split_blue_empty_all_in_red():
    assert pa_cost_split(16, 0, 1, 2) == {'red': 3, 'blue': 0}


def test_pa_cost_split_not_covered_is_none():
    assert pa_cost_split(2, 1, 2, 3) is None
    assert pa_cost_split(0, 0, 0, 1) is None
    # Own red cost not met, even with blue to spare
    assert pa_cost_split(1, 8, 2, 0) is None


def test_pa_cost_split_exact_boundary():
    """ Red available exactly equals the own red cost plus the shortfall. """
    assert pa_cost_split(4, 1, 2, 3) == {'red': 4, 'blue': 1}
    assert pa_cost_split(3, 1, 2, 3) is None
    assert pa_cost_split(0, 2, 0, 2) == {'red': 0, 'blue': 2}


def test_pa_cost_split_zero_costs():
    assert pa_cost_split(0, 0, 0, 0) == {'red': 0, 'blue': 0}
    assert pa_cost_split(16, 8, 0, 0) == {'red': 0, 'blue': 0}


def test_pa_cost_split_negative_availability_counts_as_zero():
    assert pa_cost_split(16, -3, 0, 2) == {'red': 2, 'blue': 0}
    assert pa_cost_split(-1, 8, 0, 0) == {'red': 0, 'blue': 0}
    assert pa_cost_split(-1, 8, 1, 0) is None


def test_pa_spend_split_has_no_affordability_gate():
    """ Same formula as pa_cost_split(), used by consume_pa() on a check/consume race. """
    assert pa_spend_split(1, 2, 3) == {'red': 4, 'blue': 1}
    assert pa_spend_split(-3, 0, 2) == {'red': 2, 'blue': 0}


def test_pa_shortfall_colour_affordable_is_none():
    assert pa_shortfall_colour(16, 1, 2, 3) is None
    assert pa_shortfall_colour(0, 0, 0, 0) is None


def test_pa_shortfall_colour_own_red_cost_not_met_is_red():
    assert pa_shortfall_colour(1, 8, 2, 0) == 'red'
    assert pa_shortfall_colour(1, 0, 2, 3) == 'red'


def test_pa_shortfall_colour_blue_shortfall_not_coverable_is_blue():
    assert pa_shortfall_colour(2, 1, 2, 3) == 'blue'
    assert pa_shortfall_colour(0, 0, 0, 1) == 'blue'


def test_pa_shortfall_colour_negative_red_without_red_cost_is_blue():
    """ Red overspent by a check/consume race: an action with no red cost is short on blue. """
    assert pa_shortfall_colour(-1, 0, 0, 1) == 'blue'


def test_red_only_cost_ignores_the_blue_pool():
    """ Red-only actions (reload, ruling Q15): blue is neither required nor spent. """
    assert pa_shortfall_colour(3, 0, 3, 0) is None
    assert pa_shortfall_colour(2, 8, 3, 0) == 'red'
    assert pa_cost_split(3, 8, 3, 0) == {'red': 3, 'blue': 0}
    assert pa_spend_split(8, 3, 0) == {'red': 3, 'blue': 0}


#
# get_pa() / consume_pa() against fakeredis
#
@pytest.fixture
def pa_redis(monkeypatch):
    """
    utils.redis imports `variables` for env_vars. Inside api/tests that name
    resolves to tests/variables.py (loaded by conftest), not api/variables.py
    (which connects to Mongo at import), so env_vars is provided here, then
    the Redis client is swapped for an in-memory fakeredis.
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

    monkeypatch.setattr(utils_redis, 'r', fakeredis.FakeStrictRedis(server=fakeredis.FakeServer()))
    return utils_redis


def test_get_pa_full_pools(pa_redis):
    pa = pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=3600)
    assert pa['red'] == {'pa': 16, 'ttnpa': 0, 'ttl': -2}
    assert pa['blue'] == {'pa': 8, 'ttnpa': 0, 'ttl': -2}


def test_consume_pa_normal_tick(pa_redis):
    """ Blue costs 2 ticks of TTL per PA, red 1 tick; reading back honours the same rule. """
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, redpa=1, bluepa=2, tick=3600)

    assert pa_redis.r.ttl(f'pytest:pas:{CREATURE_ID}:red') == 3600
    assert pa_redis.r.ttl(f'pytest:pas:{CREATURE_ID}:blue') == 14400

    pa = pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=3600)
    assert pa['red']['pa'] == 15
    assert pa['blue']['pa'] == 6


def test_consume_pa_accumulates_on_existing_key(pa_redis):
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, bluepa=1, tick=3600)
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, bluepa=1, tick=3600)

    assert pa_redis.r.ttl(f'pytest:pas:{CREATURE_ID}:blue') == 14400
    assert pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=3600)['blue']['pa'] == 6


def test_consume_pa_fast_tick(pa_redis):
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, redpa=3, bluepa=1, tick=60)

    assert pa_redis.r.ttl(f'pytest:pas:{CREATURE_ID}:red') == 180
    assert pa_redis.r.ttl(f'pytest:pas:{CREATURE_ID}:blue') == 120

    pa = pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=60)
    assert pa['red']['pa'] == 13
    assert pa['blue']['pa'] == 7


def test_consume_pa_zero_is_noop(pa_redis):
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, tick=3600)

    assert not pa_redis.r.exists(f'pytest:pas:{CREATURE_ID}:red')
    assert not pa_redis.r.exists(f'pytest:pas:{CREATURE_ID}:blue')


def test_tick_is_keyword_only_and_mandatory(pa_redis):
    """
    The silent 3600 default was the bug: tick is keyword-only and has no default,
    None must be passed explicitly to mean "not in an Instance".
    """
    with pytest.raises(TypeError):
        pa_redis.get_pa(CREATURE_ID, 3600)
    with pytest.raises(TypeError):
        pa_redis.consume_pa(CREATURE_ID, 0, 1, 3600)
    with pytest.raises(TypeError):
        pa_redis.get_pa(creatureuuid=CREATURE_ID)
    with pytest.raises(TypeError):
        pa_redis.consume_pa(creatureuuid=CREATURE_ID, bluepa=1)


#
# Red covers blue in consume_pa() (designer ruling Q104, fakeredis)
#
def assert_ttl_close(pa_redis, colour, expected):
    """ Consecutive consume_pa() calls may straddle a second: allow a 1s drift. """
    ttl = pa_redis.r.ttl(f'pytest:pas:{CREATURE_ID}:{colour}')
    assert expected - 1 <= ttl <= expected


def test_consume_pa_blue_shortfall_moves_to_red(pa_redis):
    """
    7 blue spent first (1 left), then a 1 red + 3 blue action: blue spends
    its last PA, the 2 missing blue land on the red pool on top of its own 1.
    """
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, bluepa=7, tick=3600)
    assert pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=3600)['blue']['pa'] == 1

    pa_redis.consume_pa(creatureuuid=CREATURE_ID, redpa=1, bluepa=3, tick=3600)

    # Blue pool spent only what it had: 8 * 7200
    assert_ttl_close(pa_redis, 'blue', 8 * 7200)
    # Red pool: own cost 1 + shortfall 2, at the red duration
    assert_ttl_close(pa_redis, 'red', 3 * 3600)

    pa = pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=3600)
    assert pa['blue']['pa'] == 0
    assert pa['red']['pa'] == 13


def test_consume_pa_blue_empty_all_in_red_fast_tick(pa_redis):
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, bluepa=8, tick=60)
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, bluepa=2, tick=60)

    assert_ttl_close(pa_redis, 'blue', 8 * 120)
    assert_ttl_close(pa_redis, 'red', 2 * 60)


def test_consume_pa_unaffordable_spends_anyway_without_raising(pa_redis):
    """ Check/consume race: never raise, same formula, red may go below zero. """
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, redpa=15, bluepa=8, tick=3600)

    pa_redis.consume_pa(creatureuuid=CREATURE_ID, redpa=1, bluepa=1, tick=3600)

    assert_ttl_close(pa_redis, 'blue', 8 * 7200)
    assert_ttl_close(pa_redis, 'red', 17 * 3600)


@pytest.fixture
def redis_spy(pa_redis, monkeypatch):
    """ Wraps the fakeredis client so the tests can assert Redis was never called. """
    spy = MagicMock(wraps=pa_redis.r)
    monkeypatch.setattr(pa_redis, 'r', spy)
    return spy


def test_get_pa_outside_instance_is_none(pa_redis, redis_spy):
    """ Designer ruling: outside an Instance (tick None) there are no PA, Redis is not read. """
    assert pa_redis.get_pa(creatureuuid=CREATURE_ID, tick=None) is None
    assert redis_spy.method_calls == []


def test_consume_pa_outside_instance_is_noop(pa_redis, redis_spy):
    """ Designer ruling: outside an Instance (tick None) nothing is consumed nor written. """
    pa_redis.consume_pa(creatureuuid=CREATURE_ID, redpa=2, bluepa=1, tick=None)

    assert redis_spy.method_calls == []
    assert not pa_redis.r.exists(f'pytest:pas:{CREATURE_ID}:red')
    assert not pa_redis.r.exists(f'pytest:pas:{CREATURE_ID}:blue')
