# -*- coding: utf8 -*-

import os

from loguru import logger

from mongo.models.Meta import MetaArmor, MetaRace, MetaWeapon

# Grab the environment variables
env_vars = {
    "APP_VERSION": os.environ.get("APP_VERSION") or "unknown",
    "GIT_COMMIT": os.environ.get("GIT_COMMIT") or "unknown",
    "API_ENV": os.environ.get("API_ENV", None),
    "REDIS_HOST": os.environ.get("REDIS_HOST", '127.0.0.1'),
    "REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "REDIS_BASE": int(os.environ.get("REDIS_BASE", 0)),
}
# Print the environment variables for debugging
_SENSITIVE_VARS = set()
for var, value in env_vars.items():
    if var in _SENSITIVE_VARS and value is not None:
        value = f'{value[:4]}...{value[-4:]}'
    logger.debug(f"{var}: {value}")

# API variables
# SEP_SECRET_KEY is needed here too (not just in auth/) - this service
# still verifies/revokes JWTs minted by the auth service, via the same
# secret and the same Redis blocklist keys. See main.py's JWTManager.
SEP_SECRET_KEY = os.environ['SEP_SECRET_KEY']
# SEP_INTERNAL_TOKEN guards the /internal/* routes, called service-to-service
# by the fight resolver (never by a client). Shared with the resolver through
# a k8s Secret. Unset = internal routes disabled (they answer 503).
SEP_INTERNAL_TOKEN = os.environ.get("SEP_INTERNAL_TOKEN")
if not SEP_INTERNAL_TOKEN:
    logger.warning('SEP_INTERNAL_TOKEN unset: /internal/* routes are disabled')

# YarQueue variables
YQ_BROADCAST = os.environ.get("YQ_BROADCAST", f"{env_vars['API_ENV']}:yarqueue:broadcast")
YQ_DISCORD   = os.environ.get("YQ_DISCORD", f"{env_vars['API_ENV']}:yarqueue:discord")
# PubSub variables
PS_BROADCAST = os.environ.get("PS_BROADCAST", 'ws-broadcast')
# The AI listens on ai-creature-<env> (ai/variables.py CREATURE_PATH), which
# has no env override: none here either, so both sides follow the same rule.
# str() so an unset API_ENV gives 'ai-creature-none' instead of an import crash
PS_AI_CREATURE = f"ai-creature-{str(env_vars['API_ENV']).lower()}"

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
# Off by default: StandaloneApplication hands Gunicorn an already-imported app,
# so a reloaded worker is re-forked with the same old code anyway
GUNICORN_RELOAD  = os.environ.get("GUNICORN_RELOAD", False)

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
