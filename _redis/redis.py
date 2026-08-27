# -*- coding: utf8 -*-

import json
import os
import redis
import yarqueue

from loguru import logger

from variables import env_vars

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


def consume_pa(creatureuuid: str, redpa: int = 0, bluepa: int = 0, duration: int = 3600) -> None:
    """
    Consumes a specified number of blue and/or red PAs for a Creature.

    :param creatureuuid: The UUID of the creature.
    :param redpa: The number of red PAs to consume (default is 0).
    :param bluepa: The number of blue PAs to consume (default is 0).
    :param duration: The duration of each PA in seconds (default is 3600 seconds).
    """
    ttls = {
        "blue": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue"),
        "red": r.ttl(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red"),
    }

    if bluepa > 0:
        logger.trace(f'Consuming PA (blue:{bluepa})')
        new_ttl = ttls['blue'] + (bluepa * duration)
        if ttls['blue'] > 0:
            # Key still exists (PA count < PA max)
            r.expire(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue", new_ttl)
        else:
            # Key does not exist anymore (PA count = PA max)
            r.set(f"{env_vars['API_ENV']}:pas:{creatureuuid}:blue", 'None', ex=new_ttl)

    if redpa > 0:
        logger.trace(f'Consuming PA (red:{redpa})')
        new_ttl = ttls['red'] + (redpa * duration)
        if ttls['red'] > 0:
            # Key still exists (PA count < PA max)
            r.expire(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red", new_ttl)
        else:
            # Key does not exist anymore (PA count = PA max)
            r.set(f"{env_vars['API_ENV']}:pas:{creatureuuid}:red", 'None', ex=new_ttl)


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
