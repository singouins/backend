# -*- coding: utf8 -*-

import os

from loguru import logger

# Grab the environment variables
env_vars = {
    "API_ENV": os.environ.get("API_ENV", None),
    "REDIS_HOST": os.environ.get("REDIS_HOST", '127.0.0.1'),
    "REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "REDIS_BASE": int(os.environ.get("REDIS_BASE", 0)),
    "SMTP_FROM": os.environ['SEP_SMTP_FROM'],
    "SMTP_SERVER": os.environ['SEP_SMTP_SERVER'],
    "SMTP_USER": os.environ['SEP_SMTP_USER'],
    "SMTP_PASS": os.environ['SEP_SMTP_PASS'],
    "SMTP_HOSTNAME": os.environ['SEP_SMTP_HOSTNAME'],
}
# Print the environment variables for debugging
for var, value in env_vars.items():
    logger.debug(f"{var}: {value}")

# Auth variables
SEP_SECRET_KEY = os.environ['SEP_SECRET_KEY']
TOKEN_DURATION = int(os.environ.get("SEP_TOKEN_DURATION", 60))
API_URL = os.environ.get("API_URL", 'http://127.0.0.1:5000')

# Discord permanent invite link
DISCORD_URL = os.environ.get("SEP_DISCORD_URL", 'http://127.0.0.1')

# Gunicorn variables
GUNICORN_CHDIR   = os.environ.get("GUNICORN_CHDIR", '/code')
GUNICORN_HOST    = os.environ.get("GUNICORN_HOST", "0.0.0.0")
GUNICORN_PORT    = os.environ.get("GUNICORN_PORT", 5000)
GUNICORN_BIND    = f'{GUNICORN_HOST}:{GUNICORN_PORT}'
GUNICORN_WORKERS = os.environ.get("GUNICORN_WORKERS", 1)
GUNICORN_THREADS = os.environ.get("GUNICORN_THREADS", 2)
GUNICORN_RELOAD  = os.environ.get("GUNICORN_RELOAD", True)

# GitHub check to position relative paths correctly
if os.environ.get("CI"):
    # Here we are inside GitHub CI process
    DATA_PATH = 'auth/data'
else:
    DATA_PATH = 'data'
