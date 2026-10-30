# -*- coding: utf8 -*-

import json
import os
import redis
import yarqueue

from loguru import logger
from typing import Optional

from utils.pa import (
    BLUE_PA_MAX,
    RED_PA_MAX,
    pa_cost_split,
    pa_durations,
    pa_from_ttl,
    pa_spend_split,
    ttl_after_spend,
    )
from variables import env_vars

# This used to be a symlink to a connector shared with auth/discord
# (_redis/redis.py). Each service now keeps its own real copy, trimmed to
# what it actually calls - api uses the full surface here (PA, pub/sub,
# queueing), so this file is unchanged in content, just no longer a
# symlink. See api/docs/ARCHITECTURE.md's "Redis usage" for why.

# Left unconfigured, redis-py defaults to a 100-connection pool that raises
# MaxConnectionsError as soon as it's exhausted - fine at low concurrency,
# but a service popping hundreds/thousands of concurrent workers (e.g. ai's
# one-thread-per-creature model) can blow past that fast. A blocking pool
# makes callers wait briefly for a free connection instead of failing
# outright, and the size is tunable per-deployment via env var.
REDIS_MAX_CONNECTIONS = int(os.environ.get('REDIS_MAX_CONNECTIONS', 500))
REDIS_POOL_TIMEOUT = int(os.environ.get('REDIS_POOL_TIMEOUT', 5))

try:
    pool = redis.BlockingConnectionPool(
        host=env_vars['REDIS_HOST'],
        port=env_vars['REDIS_PORT'],
        db=env_vars['REDIS_BASE'],
        max_connections=REDIS_MAX_CONNECTIONS,
        timeout=REDIS_POOL_TIMEOUT,
        )
    r = redis.StrictRedis(connection_pool=pool)
except Exception as e:
    logger.error(f'Redis Connection KO (r) [{e}]')
else:
    logger.debug(f'Redis Connection OK (r) [max_connections:{REDIS_MAX_CONNECTIONS}]')


def str2bool(value: str) -> bool:
    _MAP = {
        'true': True,
        'on': True,
        'false': False,
        'off': False
    }
    try:
        return _MAP[str(value).lower()]
    except KeyError:
        raise ValueError('"{}" is not a valid bool value'.format(value))


def str2typed(string: str):
    """
    Convert a string to its appropriate Python data type.

    This function checks if the string represents None, a boolean, or an integer,
    and returns the corresponding typed value. If none of these apply, it returns
    the string as-is.

    :param string: The input string to be converted.

    :return: The appropriately typed value: None, bool, int, or str.
    """
    # Normalize the input by stripping whitespace and converting to lc
    # Check if the string matches any known representations of None
    if string.strip().lower() in ("none", "null", "nil", ""):
        return None

    # Check if the string can be interpreted as a boolean
    try:
        return str2bool(string)
    except ValueError:
        pass

    # Check if the string is an integer
    try:
        return int(string)
    except ValueError:
        pass
    else:
        return string

    # Check if the string is a valid JSON object
    try:
        return json.loads(string)
    except (json.JSONDecodeError, TypeError):
        pass

    # Otherwise, return the string itself
    return string


def get_pa(creatureuuid: str, *, tick: Optional[int]) -> Optional[dict]:
    """
    Retrieves the blue and red PA and their TTL for a Creature.

    :param creatureuuid: The UUID of the creature.
    :param tick: The tick (seconds) of the Creature's Instance, see utils.pa.instance_tick().
                 Red regenerates 1 PA per tick, blue 1 PA per 2 ticks.
                 Mandatory: pass None explicitly when the Creature is not in an Instance,
                 there are no pools then, Redis is not touched and None is returned.

    :return: A dictionary with PA and TTL information for both blue and red,
             or None when the Creature is not in an Instance.
    """
    if tick is None:
        return None

    durations = pa_durations(tick)

    ttls = {
        "blue": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue"),
        "red": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red"),
    }

    return {
        "blue": pa_from_ttl(ttls['blue'], BLUE_PA_MAX, durations['blue']),
        "red": pa_from_ttl(ttls['red'], RED_PA_MAX, durations['red']),
    }


def consume_pa(
    creatureuuid: str,
    redpa: int = 0,
    bluepa: int = 0,
    *,
    tick: Optional[int],
) -> None:
    """
    Consumes a specified number of blue and/or red PAs for a Creature.

    Designer ruling Q104 ("red PA pay for everything"): the blue cost is spent
    from the blue pool as far as it goes, the shortfall is spent from the red
    pool on top of the red cost (see utils.pa.pa_cost_split()).

    :param creatureuuid: The UUID of the creature.
    :param redpa: The red PA cost of the action (default is 0).
    :param bluepa: The blue PA cost of the action (default is 0),
                   red PA cover what the blue pool lacks.
    :param tick: The tick (seconds) of the Creature's Instance, see utils.pa.instance_tick().
                 Each red PA spent costs one tick of TTL, each blue PA two ticks.
                 Mandatory: pass None explicitly when the Creature is not in an Instance,
                 there are no pools then, nothing is consumed and Redis is not touched.
    """
    if tick is None:
        logger.trace(f'[Creature.id:{creatureuuid}] not in an Instance: no PA to consume')
        return

    durations = pa_durations(tick)

    ttls = {
        "blue": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue"),
        "red": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red"),
    }

    # Designer ruling Q104: blue is spent first, red covers the blue shortfall
    available = {
        "blue": pa_from_ttl(ttls['blue'], BLUE_PA_MAX, durations['blue'])['pa'],
        "red": pa_from_ttl(ttls['red'], RED_PA_MAX, durations['red'])['pa'],
    }
    split = pa_cost_split(available['red'], available['blue'], redpa, bluepa)
    if split is None:
        # The pools changed between the check and now (concurrent request):
        # spend anyway with the same formula, never raise mid-action
        split = pa_spend_split(available['blue'], redpa, bluepa)
        logger.warning(
            f'[Creature.id:{creatureuuid}] PA(red:{redpa}, blue:{bluepa}) unaffordable at consume '
            f'(available red:{available["red"]}, blue:{available["blue"]}): spending anyway'
            )
    redpa, bluepa = split['red'], split['blue']

    if bluepa > 0:
        logger.trace(f'Consuming PA (blue:{bluepa})')
        new_ttl = ttl_after_spend(ttls['blue'], bluepa, durations['blue'])
        if ttls['blue'] > 0:
            # Key still exists (PA count < PA max)
            r.expire(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue", new_ttl)
        else:
            # Key does not exist anymore (PA count = PA max)
            r.set(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue", 'None', ex=new_ttl)

    if redpa > 0:
        logger.trace(f'Consuming PA (red:{redpa})')
        new_ttl = ttl_after_spend(ttls['red'], redpa, durations['red'])
        if ttls['red'] > 0:
            # Key still exists (PA count < PA max)
            r.expire(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red", new_ttl)
        else:
            # Key does not exist anymore (PA count = PA max)
            r.set(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red", 'None', ex=new_ttl)


def _pa_keys(creatureuuid: str) -> dict:
    """ The Redis keys of a Creature's PA pools, by colour. """
    return {
        "blue": f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue",
        "red": f"{env_vars['API_ENV']}:pas:{creatureuuid}:red",
    }


def try_consume_pa(
    creatureuuid: str,
    redpa: int = 0,
    bluepa: int = 0,
    *,
    tick: Optional[int],
) -> bool:
    """
    Checks and consumes the PA of an action in one atomic step (issue #498).

    The pools are read, the cost is split with designer ruling Q104 (red PA
    cover what the blue pool lacks, see utils.pa.pa_cost_split()) and spent
    only when affordable. Two concurrent calls on one Creature cannot both
    spend the same PA.

    Atomicity: WATCH + MULTI/EXEC. The pools are read under WATCH, the spend
    is queued in MULTI. When another client changes a pool before EXEC,
    redis-py raises WatchError and reruns the whole read/split/spend on fresh
    values. Q104 stays in Python (pa_cost_split()).

    :param creatureuuid: The UUID of the creature.
    :param redpa: The red PA cost of the action (default is 0).
    :param bluepa: The blue PA cost of the action (default is 0),
                   red PA cover what the blue pool lacks.
    :param tick: The tick (seconds) of the Creature's Instance, see utils.pa.instance_tick().
                 Mandatory: pass None explicitly when the Creature is not in an Instance,
                 there are no pools then, Redis is not touched and True is returned.

    :return: True when the PA were spent (or nothing to spend), False when
             the action is not affordable: nothing is spent then.
    """
    if tick is None:
        logger.trace(f'[Creature.id:{creatureuuid}] not in an Instance: no PA to consume')
        return True

    durations = pa_durations(tick)
    keys = _pa_keys(creatureuuid)
    pa_max = {"blue": BLUE_PA_MAX, "red": RED_PA_MAX}

    def reserve(pipe) -> bool:
        # Under WATCH the pipeline runs commands immediately: these are real reads
        ttls = {colour: pipe.ttl(key) for colour, key in keys.items()}
        available = {
            colour: pa_from_ttl(ttls[colour], pa_max[colour], durations[colour])['pa']
            for colour in keys
        }
        split = pa_cost_split(available['red'], available['blue'], redpa, bluepa)

        # Queued from here, applied by EXEC only if no pool changed since the
        # reads. A refusal goes through EXEC too: it is confirmed on unchanged pools
        pipe.multi()
        if split is None:
            return False

        for colour, key in keys.items():
            if split[colour] > 0:
                new_ttl = ttl_after_spend(ttls[colour], split[colour], durations[colour])
                if ttls[colour] > 0:
                    # Key still exists (PA count < PA max)
                    pipe.expire(key, new_ttl)
                else:
                    # Key does not exist anymore (PA count = PA max)
                    pipe.set(key, 'None', ex=new_ttl)
        return True

    # Reruns until EXEC applies: no retry limit, a conflict needs another
    # write on this Creature's pools in the few ms between WATCH and EXEC
    consumed = r.transaction(reserve, keys['blue'], keys['red'], value_from_callable=True)
    if not consumed:
        logger.trace(f'[Creature.id:{creatureuuid}] PA(red:{redpa}, blue:{bluepa}) unaffordable')
    return consumed


def refund_pa(
    creatureuuid: str,
    redpa: int = 0,
    bluepa: int = 0,
    *,
    tick: Optional[int],
) -> None:
    """
    Gives back PA spent by try_consume_pa() (issue #498), atomically.

    For a refusal detected after the PA were reserved (e.g. the corpse was
    taken meanwhile). A failed roll keeps its cost: refused is not failed.
    Each pool TTL is lowered by the PA refunded times their duration; a pool
    back to full has its key deleted. A full pool (no key) stays full.

    The amounts are per pool, as spent: when red PA covered a blue shortfall
    (Q104), the covered part is refunded as red.

    :param creatureuuid: The UUID of the creature.
    :param redpa: The red PA to give back (default is 0).
    :param bluepa: The blue PA to give back (default is 0).
    :param tick: The tick (seconds) of the Creature's Instance, see utils.pa.instance_tick().
                 Mandatory: pass None explicitly when the Creature is not in an Instance,
                 there are no pools then, nothing is refunded and Redis is not touched.
    """
    if tick is None:
        logger.trace(f'[Creature.id:{creatureuuid}] not in an Instance: no PA to refund')
        return

    durations = pa_durations(tick)
    keys = _pa_keys(creatureuuid)
    amounts = {"blue": bluepa, "red": redpa}

    def refund(pipe) -> None:
        # Under WATCH the pipeline runs commands immediately: these are real reads
        ttls = {colour: pipe.ttl(key) for colour, key in keys.items()}

        pipe.multi()
        for colour, key in keys.items():
            # No TTL (-2 absent, -1 no expiry): the pool is full, nothing to give back
            if amounts[colour] <= 0 or ttls[colour] <= 0:
                continue
            new_ttl = ttls[colour] - amounts[colour] * durations[colour]
            if new_ttl > 0:
                pipe.expire(key, new_ttl)
            else:
                # Back to full: an absent key is a full pool
                pipe.delete(key)

    r.transaction(refund, keys['blue'], keys['red'])


# Every Redis key family a Creature can own while inside an Instance.
# Placeholders: {env} (API_ENV), {instance} (Instance uuid), {creature} (Creature uuid).
# The bearer segment is matched exactly (never *{creature}*): ids are uuids,
# and a key is owned by a Creature only when a whole segment is its id.
CREATURE_KEY_PATTERNS = (
    # Creature-wide PA pools, not scoped by Instance (see get_pa/consume_pa)
    '{env}:pas:{creature}:*',
    # 5-segment actives: effects/statuses/cds, a trailing name after the bearer
    # (see routes/mypc/actives.py and action/profession/tracking.py)
    '{env}:{instance}:*:{creature}:*',
    # Defensive: matches no key written today. Any future 4-segment key ending
    # with the bearer (e.g. a prefixed ammo key) is covered by construction
    '{env}:{instance}:*:{creature}',
    # The resolver's ammo key, as its contract spells it (no API_ENV prefix)
    '{instance}:ammo:{creature}',
    )


def purge_creature_keys(creatureuuid: str, instanceuuid: str) -> int:
    """
    Deletes every Redis key a Creature owns in an Instance, plus its PA pools.

    Outside an instance nothing of the creature exists in Redis (ruling 2026-10-08):
    PA pools are expiring keys (absent = full pool), actives and ammo are scoped
    by Instance. Only the Instance being left is purged, plus the creature-wide
    PA keys; actives of the same Creature in another Instance are not touched.

    Keys are found with SCAN (never KEYS in app code) and deleted in one
    DEL per pattern family.

    :param creatureuuid: The UUID of the creature.
    :param instanceuuid: The UUID of the instance being left.

    :return: The number of deleted keys.
    """
    deleted = 0
    for pattern in CREATURE_KEY_PATTERNS:
        match = pattern.format(
            env=env_vars['API_ENV'],
            instance=instanceuuid,
            creature=creatureuuid,
            )
        # count is a hint per SCAN call: fewer round trips than the default of 10
        keys = list(r.scan_iter(match=match, count=1000))
        if keys:
            deleted += r.delete(*keys)

    logger.trace(f'Purged Redis keys (creatureuuid:{creatureuuid}, deleted:{deleted})')
    return deleted


INSTANCE_KEY_PATTERNS = (
    # Everything scoped by the Instance under the API_ENV prefix: actives of
    # every bearer (players already purged on leave, mobs, anything else)
    '{env}:{instance}:*',
    # The resolver's Instance-scoped keys (no API_ENV prefix), e.g. ammo
    '{instance}:*',
    )


def purge_instance_keys(instanceuuid: str) -> int:
    """
    Deletes every Redis key scoped by an Instance, whoever the bearer is.

    Called once the Instance is closed (last player gone, mobs deleted): a
    deleted Instance takes its mobs with it, so nothing of it may outlive it
    (ruling 2026-10-08). Creature-wide keys (PA pools) are not scoped by
    Instance and are purged per creature, see purge_creature_keys().

    Keys are found with SCAN (never KEYS in app code) and deleted in one
    DEL per pattern family.

    :param instanceuuid: The UUID of the closed instance.

    :return: The number of deleted keys.
    """
    deleted = 0
    for pattern in INSTANCE_KEY_PATTERNS:
        match = pattern.format(env=env_vars['API_ENV'], instance=instanceuuid)
        # count is a hint per SCAN call: fewer round trips than the default of 10
        keys = list(r.scan_iter(match=match, count=1000))
        if keys:
            deleted += r.delete(*keys)

    logger.trace(f'Purged Redis keys (instanceuuid:{instanceuuid}, deleted:{deleted})')
    return deleted


def cput(channel: str, msg: dict) -> None:
    """
    Publishes a message (dict) to a specified Redis PubSub channel.

    :param channel: Name of the Redis channel to publish to.
    :param msg: The message dictionary to be published.
    """
    try:
        logger.trace(f'Pubsub PUBLISH >> (channel:{channel})')
        r.publish(channel, json.dumps(msg))
    except Exception as e:
        msg = (f'Pubsub PUBLISH KO (channel:{channel}) [{e}]')
        logger.error(msg)
    else:
        logger.trace(f'Pubsub PUBLISH OK (channel:{channel})')


def qput(queue: str, msg: dict) -> None:
    """
    Publishes a message (dict) to a specified Redis YarQueue.

    :param channel: Name of the Redis channel to publish to.
    :param msg: The message dictionary to be published.
    """
    try:
        logger.trace(f'Queue PUT >> (queue:{queue})')
        yqueue = yarqueue.Queue(name=queue, redis=r)
        json_msg = json.dumps(msg)
        yqueue.put(json_msg)
    except Exception as e:
        logger.error(f'Queue PUT KO (queue:{queue}) [{e}]')
    else:
        logger.trace(f'Queue PUT OK (queue:{queue})')
