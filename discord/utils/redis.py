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
# actually calls: get_pa (read-only PA checks) and cput (pub/sub). No
# consume_pa, qput, or str2typed here - discord doesn't consume PA, and it
# consumes queues via yarqueue directly (see subtasks/yqueue.py) rather
# than through this module's producer-side qput helper.
# discord/variables.py already has its own str2bool, unrelated to this
# file. See api/docs/ARCHITECTURE.md's "Redis usage" for why the symlink
# got dropped.


def get_pa(creatureuuid: str, duration: int = 3600) -> dict:
    """
    Retrieves the blue and red PA and their TTL for a Creature.

    :param creatureuuid: The UUID of the creature.
    :param duration: The duration in seconds for PA calculation. Default is 3600 seconds (1 hour).

    :return: A dictionary with PA and TTL information for both blue and red.
    """
    # Constants
    RED_PA_MAX = 16
    RED_PA_MAXTTL = RED_PA_MAX * duration
    BLUE_PA_MAX = 8
    BLUE_PA_MAXTTL = BLUE_PA_MAX * duration

    ttls = {
        "blue": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue"),
        "red": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red"),
    }

    return {
        "blue": {
            "pa": int(round((BLUE_PA_MAXTTL - abs(ttls['blue'])) / duration)),
            "ttnpa": ttls['blue'] % duration,
            "ttl": ttls['blue'],
        },
        "red": {
            "pa": int(round((RED_PA_MAXTTL - abs(ttls['red'])) / duration)),
            "ttnpa": ttls['red'] % duration,
            "ttl": ttls['red'],
        },
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
