# -*- coding: utf8 -*-

import os
import redis
import uuid

GUNICORN_PORT   = os.environ.get("GUNICORN_PORT", 5000)
API_ENV         = os.environ.get("API_ENV", 5000)
API_URL         = f'http://127.0.0.1:{GUNICORN_PORT}'

# /auth/* moved to its own service - api's own tests still need a live
# login to test everything else, so this points at wherever that service
# is reachable (see api/scripts/test-local.sh, which boots both).
AUTH_GUNICORN_PORT = os.environ.get("AUTH_GUNICORN_PORT", 5001)
AUTH_API_URL       = os.environ.get("AUTH_API_URL", f'http://127.0.0.1:{AUTH_GUNICORN_PORT}')

r = redis.StrictRedis(
    host=os.environ.get("REDIS_HOST", '127.0.0.1'),
    port=os.environ.get("REDIS_PORT", 6379),
    db=os.environ.get("REDIS_BASE", 0),
    encoding='utf-8',
    )

# Creature ID variables
# The CREATURE_ID is supposed to be built with
# uuid.uuid3(uuid.NAMESPACE_DNS, CREATURE_NAME)
CREATURE_NAME   = 'PJTest'
CREATURE_ID     = str(uuid.uuid3(uuid.NAMESPACE_DNS, CREATURE_NAME))
USER_NAME       = 'user@exemple.net'
USER_ID         = str(uuid.uuid3(uuid.NAMESPACE_DNS, USER_NAME))
SQUAD_ID        = str(uuid.uuid3(uuid.NAMESPACE_DNS, CREATURE_NAME))

AUTH_PAYLOAD    = {'username': USER_NAME, 'password': 'plop'}
MAP_ID          = 1
METAS           = ['armor', 'weapon', 'race']

PJTEST_BODY = {
    'name': CREATURE_NAME,
    'gender': True,
    'race': 2,
    'vocation': 3,
    'cosmetic': {
        'metaid': 8,
        'data': {
            'hasGender': True,
            'beforeArmor': False,
            'hideArmor': None,
        }
    },
    'equipment': {
        'righthand': {
            'metaid': 34,
            'metatype': 'weapon'
        },
        'lefthand': {
            'metaid': 11,
            'metatype': 'weapon'
        }
    }
}
