# -*- coding: utf8 -*-

import os

from loguru import logger

from mongo.models.Meta import MetaArmor, MetaRace, MetaWeapon

# Grab the environment variables
env_vars = {
    "API_ENV": os.environ.get("API_ENV", None),
    "REDIS_HOST": os.environ.get("REDIS_HOST", '127.0.0.1'),
    "REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "REDIS_BASE": int(os.environ.get("REDIS_BASE", 0)),
}
# Print the environment variables for debugging
for var, value in env_vars.items():
    logger.debug(f"{var}: {value}")

# API variables
# SEP_SECRET_KEY is needed here too (not just in auth/) - this service
# still verifies/revokes JWTs minted by the auth service, via the same
# secret and the same Redis blocklist keys. See main.py's JWTManager.
SEP_SECRET_KEY = os.environ['SEP_SECRET_KEY']

# YarQueue variables
YQ_BROADCAST = os.environ.get("YQ_BROADCAST", f"{env_vars['API_ENV']}:yarqueue:broadcast")
YQ_DISCORD   = os.environ.get("YQ_DISCORD", f"{env_vars['API_ENV']}:yarqueue:discord")
# PubSub variables
PS_BROADCAST = os.environ.get("PS_BROADCAST", 'ws-broadcast')

# Resolver variables
RESOLVER_HOST = os.environ.get("RESOLVER_HOST", 'resolver-svc')
RESOLVER_PORT = os.environ.get("RESOLVER_PORT", 3000)
RESOLVER_URL  = f'http://{RESOLVER_HOST}:{RESOLVER_PORT}'

# Gunicorn variables
GUNICORN_CHDIR   = os.environ.get("GUNICORN_CHDIR", '/code')
GUNICORN_HOST    = os.environ.get("GUNICORN_HOST", "0.0.0.0")
GUNICORN_PORT    = os.environ.get("GUNICORN_PORT", 5000)
GUNICORN_BIND    = f'{GUNICORN_HOST}:{GUNICORN_PORT}'
GUNICORN_WORKERS = os.environ.get("GUNICORN_WORKERS", 1)
GUNICORN_THREADS = os.environ.get("GUNICORN_THREADS", 2)
GUNICORN_RELOAD  = os.environ.get("GUNICORN_RELOAD", True)

# Static data
rarity_levels = {
    'creature': ['Small', 'Medium', 'Big', 'Unique', 'Boss', 'God'],
    'standard': ['Broken', 'Common', 'Uncommon', 'Rare', 'Epic', 'Legendary']
}

rarity_array = {
    'creature': rarity_levels['creature'],
    'resource': rarity_levels['standard'],
    'item': rarity_levels['standard'],
}

"""
DISCLAIMER: This is some fat shit I dumped here

This is a HUGE Dictionary to manipulate pore easiliy all the metas
Without having to query MongoDB all the time internally

Do not modifiy unless you're ready for consequences
"""
metaNames = {
    'armor': [doc.to_mongo().to_dict() for doc in MetaArmor.objects()],
    'weapon': [doc.to_mongo().to_dict() for doc in MetaWeapon.objects()],
    'race': [doc.to_mongo().to_dict() for doc in MetaRace.objects()]
}

metaIndexed = {
    'armor': {armor["_id"]: armor for armor in metaNames['armor']},
    'weapon': {weapon["_id"]: weapon for weapon in metaNames['weapon']},
    'race': {race["_id"]: race for race in metaNames['race']},
}
