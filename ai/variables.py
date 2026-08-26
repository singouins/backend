# -*- coding: utf8 -*-

import os

from loguru import logger
from prometheus_client import Gauge, Histogram

# Prometheus metrics
THREAD_COUNT_TOTAL = Gauge('thread_count_total', 'Number of threads (total)')
THREAD_COUNT_FUNGUS = Gauge('thread_count_fungus', 'Number of Fungus threads')
THREAD_COUNT_SALAMANDER = Gauge('thread_count_salamander', 'Number of Salamander threads')
CREATURE_TICK_DURATION = Histogram(
    'creature_tick_seconds',
    'Time spent processing one creature tick (excludes the deliberate sleep)',
    ['species'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    )

# Fraction of an Instance's tick budget a single creature's processing can
# consume before we log a "getting close to blowing the tick" warning.
TICK_OVERRUN_THRESHOLD = 0.8

# Grab the environment variables
env_vars = {
    "API_ENV": os.environ.get("API_ENV", None),
    "REDIS_HOST": os.environ.get("REDIS_HOST", '127.0.0.1'),
    "REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "REDIS_BASE": int(os.environ.get("REDIS_BASE", 0)),
    "RESOLVER_HOST": os.environ.get("RESOLVER_HOST", 'resolver-svc'),
    "RESOLVER_PORT": os.environ.get("RESOLVER_PORT", 3000),
    "RESOLVER_CHECK_SKIP": os.environ.get("RESOLVER_CHECK_SKIP"),
    "INSTANCE_PATH": f'ai-instance-{os.environ.get("API_ENV", None).lower()}',
    "CREATURE_PATH": f'ai-creature-{os.environ.get("API_ENV", None).lower()}',
}
env_vars['RESOLVER_URL'] = f"http://{env_vars['RESOLVER_HOST']}:{env_vars['RESOLVER_PORT']}"

# Print the environment variables for debugging
for var, value in env_vars.items():
    logger.debug(f"{var}: {value}")
