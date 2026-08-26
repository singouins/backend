# -*- coding: utf8 -*-

import json
import requests

from loguru import logger

from variables import env_vars


def resolver_generic_request_get(path, code=200):
    try:
        response = requests.get(f"{env_vars['RESOLVER_URL']}{path}", timeout=(1, 1))
    except Exception as e:
        logger.error(f'Request Query KO [{e}]')
        return None
    else:
        return check_response(response, 200)


def resolver_move(self, targetx, targety):
    body = {
        "fightEvent": {
            "name": "RegularMovesFightClass",
            "type": 3,
            "actor": self.creature.id,
            "params": {
                "destinationType": "tile",
                "destination": None,
                "options": {
                    "path": [{"x": targetx, "y": targety}]
                    },
                "type": "target",
                },
            },
        }

    try:
        response = requests.post(f"{env_vars['RESOLVER_URL']}/", json=body, timeout=(1, 1))
    except Exception as e:
        logger.error(f'Request Query KO [{e}]')
        return None
    else:
        return check_response(response, 201)


def resolver_basic_attack(self, target):
    body = {
        "fightEvent": {
            "name": "RegularAttacksFightClass",
            "type": 0,
            "actor": self.creature.id,
            "params": {
                "type": "target",
                "destinationType": "creature",
                "destination": target['id'],
                "options": {
                    "weapons": [],
                    "burst": False,
                    "doubleBarrel": False,
                    "scope": False,
                    },
                },
            },
        }

    try:
        response = requests.post(f"{env_vars['RESOLVER_URL']}/", json=body, timeout=(1, 1))
    except Exception as e:
        logger.error(f'Request Query KO [{e}]')
        return None
    else:
        return check_response(response, 200)

#
# Checkers
#


def check_response(response, code):
    logger.trace('HTTP response Headers:' + str(response.headers))
    logger.trace('HTTP response Code:' + str(response.status_code))
    logger.trace('HTTP response Body:' + str(response.text))

    if response:
        if response.status_code == code:
            if response.text:
                logger.trace(f'Request {response.status_code} OK ({json.loads(response.text)})')
                return json.loads(response.text)
            else:
                logger.warning(f'Request {response.status_code} KO')
                return None
        else:
            if response.text:
                logger.trace(f'Request {response.status_code} KO ({json.loads(response.text)})')
                return None
            else:
                logger.warning(f'Request {response.status_code} KO')
                return None
    else:
        logger.warning('Request Query KO')
        return None
