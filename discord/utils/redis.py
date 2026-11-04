# -*- coding: utf8 -*-

import json
import os
import redis

from loguru import logger

from variables import env_vars

# Left unconfigured, redis-py defaults to a 100-connection pool that raises
# MaxConnectionsError as soon as it's exhausted - fine at low concurrency,
# but a service popping hundreds/thousands of concurrent workers can blow
# past that fast. A blocking pool makes callers wait briefly for a free
# connection instead of failing outright, and the size is tunable per-
# deployment via env var.
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

# This used to be a symlink to a connector shared with api/auth
# (_redis/redis.py) - now a real, trimmed-down file with only what discord
# actually calls: get_pa (read-only PA checks), cput (pub/sub) and the
# Discord link code helpers (bottom of the file). No
# consume_pa, qput, or str2typed here - discord doesn't consume PA, and it
# consumes queues via yarqueue directly (see subtasks/yqueue.py) rather
# than through this module's producer-side qput helper.
# discord/variables.py already has its own str2bool, unrelated to this
# file. See api/docs/ARCHITECTURE.md's "Redis usage" for why the symlink
# got dropped.


def get_pa(creatureuuid: str, *, tick: int) -> dict:
    """
    Retrieves the blue and red PA and their TTL for a Creature.

    Reads both pools with FCALL_RO pa_read, from the Redis function library
    functions_pa (Lordslair's, deployed with the databases chart; source of
    truth: singouins/helm). The API, ai and the resolver read the same way:
    a PA only counts once fully regenerated, pa = max - ceil(remaining / duration),
    ttnpa is 1..duration while the pool regenerates, 0 when it is full.

    :param creatureuuid: The UUID of the creature.
    :param tick: The tick (seconds) of the Creature's Instance (InstanceDocument.tick).
                 Red regenerates 1 PA per tick, blue 1 PA per 2 ticks - same rule as
                 api/utils/pa.py. Outside an Instance there are no PA: do not call this.

    :return: A dictionary with PA and TTL information for both blue and red,
             {'pa', 'ttnpa', 'ttl'} each, ttl being the raw Redis TTL.
    """
    # Constants
    RED_PA_MAX = 16
    BLUE_PA_MAX = 8
    RED_PA_DURATION = tick
    BLUE_PA_DURATION = 2 * tick

    # KEYS: blue first; ARGV: red first
    red_pa, red_ttnpa, red_ttl, blue_pa, blue_ttnpa, blue_ttl = r.fcall_ro(
        'pa_read', 2,
        f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue",
        f"{env_vars['API_ENV']}:pas:{creatureuuid}:red",
        RED_PA_DURATION, BLUE_PA_DURATION, RED_PA_MAX, BLUE_PA_MAX,
        )

    return {
        "blue": {"pa": blue_pa, "ttnpa": blue_ttnpa, "ttl": blue_ttl},
        "red": {"pa": red_pa, "ttnpa": red_ttnpa, "ttl": red_ttl},
    }


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


# Discord link codes: issued by auth (POST /discord/link, see
# auth/utils/token.py's generate_discord_link_code()) to a logged-in User,
# consumed here by /user link. Same key name on both sides - keep in sync.
LINK_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # No 0/O, 1/I
LINK_CODE_LENGTH = 8
# Brute-force guard: attempts allowed per Discord user, per window
LINK_ATTEMPTS_MAX = 5
LINK_ATTEMPTS_WINDOW = 600  # 10 minutes, in seconds


def link_code_consume(code: str) -> str | None:
    """
    Consumes a Discord link code: it can be used once only.

    :param code: The normalized code (LINK_CODE_LENGTH chars, no dash).

    :return: The UUID (str) of the User the code was issued to, or None if
             the code is unknown, expired or already used.
    """
    key = f"{env_vars['API_ENV']}:discord:link_code:{code}"
    # MULTI/EXEC: two concurrent callers can't both get the User
    pipe = r.pipeline(transaction=True)
    pipe.get(key)
    pipe.delete(key)
    useruuid, _ = pipe.execute()
    return useruuid.decode() if useruuid is not None else None


def link_attempts_incr(discordid: int) -> int:
    """
    Counts a /user link attempt of a Discord user, in a window of
    LINK_ATTEMPTS_WINDOW seconds starting at its first attempt.

    :param discordid: The Discord user id (stable, unlike the name).

    :return: The number of attempts in the current window, this one included.
    """
    key = f"{env_vars['API_ENV']}:discord:link_attempts:{discordid}"
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.ttl(key)
    attempts, ttl = pipe.execute()
    # -1: no expiry yet (first attempt, or a previous EXPIRE got lost),
    # never leave the counter without one or the user is locked out for good
    if ttl == -1:
        r.expire(key, LINK_ATTEMPTS_WINDOW)
    return attempts
