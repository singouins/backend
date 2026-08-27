# -*- coding: utf8 -*-

# Unlike api/discord, ai talks to Redis entirely asynchronously (see
# ARCHITECTURE.md's asyncio rework) - it can't share the synchronous client
# in _redis/redis.py, so this is ai's own, non-shared client rather than a
# symlink to that shared module.

import os

import redis.asyncio as redis
from loguru import logger

from variables import env_vars

# Same reasoning as _redis/redis.py: an unconfigured pool defaults to 100
# connections and raises outright once exhausted, which is exactly what
# crashed threads under load before this was sized (see ARCHITECTURE.md).
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
    r = redis.Redis(connection_pool=pool)
except Exception as e:
    logger.error(f'Redis Connection KO (r) [{e}]')
else:
    logger.debug(f'Redis Connection OK (r) [max_connections:{REDIS_MAX_CONNECTIONS}]')
