# -*- coding: utf8 -*-

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

# This used to be a symlink to a connector shared with api/discord
# (_redis/redis.py) - now a real, trimmed-down file with only what auth
# actually calls (r.get/set/delete for JWT jti tracking and confirm/reset
# tokens - see utils/auth.py and utils/token.py). No PA helpers, pub/sub,
# or queueing here - auth never uses them, and importing them would pull
# in yarqueue for nothing. See api/docs/ARCHITECTURE.md's "Redis usage"
# for why the symlink got dropped.
