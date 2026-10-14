# -*- coding: utf8 -*-

# Pure Action Points (PA) arithmetic, shared by utils/redis.py (read/consume)
# and the decorators. Deliberately stdlib-only at module level so it can be
# unit-tested without a Mongo/Redis connection (see tests/test_00_pa.py).
#
# PA pools live in Redis as `{API_ENV}:pas:{creatureuuid}:red|blue` whose TTL
# is the time left until the pool is full again. A missing key (TTL -2, or -1
# with no expiry) means the pool is full.
#
# Designer ruling: outside an Instance there are no PA at all (no Redis read,
# no Redis write). instance_tick() returns None in that case and the callers
# skip the pools entirely.

from typing import Optional

RED_PA_MAX = 16
BLUE_PA_MAX = 8

# Designer rulings Q102 + Q108: equipping an item costs red PA by item size,
# no blue PA. Unequipping stays free (Q109).
EQUIP_RED_PA_BY_SIZE = {
    '1x2': 1,
    '2x2': 2,
    '2x3': 3,
    '2x4': 4,
    '3x4': 4,
}


def pa_durations(tick: int) -> dict:
    """
    Seconds needed to regenerate one PA of each colour for a given Instance tick.

    Designer ruling: red regenerates 1 PA per Instance tick, blue 1 PA per
    2 Instance ticks. The combat resolver reads the pools with the same rule.

    :param tick: The Instance tick, in seconds.

    :return: {'red': tick, 'blue': 2 * tick}
    """
    return {
        'red': tick,
        'blue': 2 * tick,
    }


def pa_from_ttl(ttl: int, pa_max: int, duration: int) -> dict:
    """
    Converts the Redis TTL of a PA pool into the PA available right now.

    :param ttl: The raw TTL returned by Redis (negative when the key is absent).
    :param pa_max: The pool size (RED_PA_MAX or BLUE_PA_MAX).
    :param duration: Seconds needed to regenerate one PA (see pa_durations()).

    :return: {'pa': available PA, 'ttnpa': seconds to the next PA, 'ttl': the raw TTL}
    """
    # A negative TTL (-2 key absent, -1 no expiry) counts as nothing to wait for
    remaining = max(ttl, 0)

    return {
        'pa': int(round((pa_max * duration - remaining) / duration)),
        'ttnpa': remaining % duration,
        'ttl': ttl,
    }


def ttl_after_spend(ttl: int, spent: int, duration: int) -> int:
    """
    New TTL of a PA pool after spending some PA.

    :param ttl: The raw TTL returned by Redis (negative when the key is absent).
    :param spent: The number of PA spent.
    :param duration: Seconds needed to regenerate one PA (see pa_durations()).

    :return: The TTL to apply on the pool key, in seconds.
    """
    return max(ttl, 0) + spent * duration


def pa_cost_split(
    red_available: int,
    blue_available: int,
    red_cost: int,
    blue_cost: int,
) -> Optional[dict]:
    """
    Splits the PA cost of an action between the red and blue pools.

    Designer ruling Q104 ("red PA pay for everything"): when an action costs
    blue PA and the Creature lacks blue, red PA cover the shortfall, 1 red per
    missing blue. Blue is spent first, the shortfall is added to the action's
    own red cost.

    :param red_available: Red PA available right now (negative counts as 0).
    :param blue_available: Blue PA available right now (negative counts as 0).
    :param red_cost: Red PA cost of the action.
    :param blue_cost: Blue PA cost of the action.

    :return: {'red': red PA to spend, 'blue': blue PA to spend},
             or None when the red pool cannot cover its share.
    """
    split = pa_spend_split(blue_available, red_cost, blue_cost)

    if max(red_available, 0) < split['red']:
        return None

    return split


def pa_shortfall_colour(
    red_available: int,
    blue_available: int,
    red_cost: int,
    blue_cost: int,
) -> Optional[str]:
    """
    Colour to report when an action is refused for lack of PA.

    'red' when the action's own red cost is not met, 'blue' when the blue
    shortfall cannot be covered by red (designer ruling Q104), None when the
    action is affordable (see pa_cost_split()).

    :param red_available: Red PA available right now (negative counts as 0).
    :param blue_available: Blue PA available right now (negative counts as 0).
    :param red_cost: Red PA cost of the action.
    :param blue_cost: Blue PA cost of the action.

    :return: 'red', 'blue', or None when affordable.
    """
    if pa_cost_split(red_available, blue_available, red_cost, blue_cost) is not None:
        return None

    return 'red' if max(red_available, 0) < red_cost else 'blue'


def pa_spend_split(blue_available: int, red_cost: int, blue_cost: int) -> dict:
    """
    The pa_cost_split() formula without the affordability gate: blue spent
    first, the blue shortfall added to the red cost.

    Used by consume_pa() when the pools changed between the check and the
    consumption: the PA are still spent deterministically, never raised.

    :param blue_available: Blue PA available right now (negative counts as 0).
    :param red_cost: Red PA cost of the action.
    :param blue_cost: Blue PA cost of the action.

    :return: {'red': red PA to spend, 'blue': blue PA to spend}
    """
    blue_spent = min(blue_cost, max(blue_available, 0))
    shortfall = blue_cost - blue_spent

    return {
        'red': red_cost + shortfall,
        'blue': blue_spent,
    }


def equip_cost(size: str) -> Optional[dict]:
    """
    PA cost of equipping an item, by item size.

    Designer rulings Q102 + Q108: red PA only, by size (see EQUIP_RED_PA_BY_SIZE).

    :param size: The item size from its meta, e.g. '2x3'.

    :return: {'red': red PA cost, 'blue': 0}, or None for a size not in the table.
    """
    red = EQUIP_RED_PA_BY_SIZE.get(size)
    if red is None:
        return None

    return {
        'red': red,
        'blue': 0,
    }


def instance_tick(creature) -> Optional[int]:
    """
    Tick of the Instance the Creature is in, or None when it is in none
    (or the Instance no longer exists): not in an Instance means no PA.

    Reuses flask's g.Instance when a decorator already loaded it for this
    request, to avoid a second Mongo query.

    :param creature: The CreatureDocument.

    :return: The tick in seconds, or None (not in an Instance: no PA).
    """
    # Lazy imports keep this module importable without a Mongo connection for the unit tests
    from flask import g
    from loguru import logger
    from mongo.models.Instance import InstanceDocument

    if not creature.instance:
        return None

    Instance = getattr(g, 'Instance', None)
    if Instance is not None and Instance.id == creature.instance:
        return Instance.tick

    try:
        return InstanceDocument.objects(_id=creature.instance).get().tick
    except InstanceDocument.DoesNotExist:
        logger.warning(
            f'[Creature.id:{creature.id}] InstanceDocument({creature.instance}) NOTFOUND: no PA'
            )
        return None
