# -*- coding: utf8 -*-

import json

import httpx
from loguru import logger

from variables import env_vars

TIMEOUT = httpx.Timeout(connect=1, read=1, write=1, pool=1)


async def resolver_generic_request_get(path, code=200):
    """
    Sends a GET request to the Resolver.

    Parameters:
        - path: STR - path appended to RESOLVER_URL (e.g. "/check")
        - code: INT - intended expected HTTP status code; currently unused,
          check_response() is always called with 200 regardless of this
          value

    Returns: dict (parsed JSON body), or None on request failure or an
    unexpected response
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{env_vars['RESOLVER_URL']}{path}")
    except Exception as e:
        logger.error(f'Request Query KO [{e}]')
        return None
    else:
        return check_response(response, 200)


async def resolver_move(self, targetx, targety):
    """
    Requests the Resolver to move a Creature to a given tile.

    Parameters:
        - self: Mob instance (the calling Creature)
        - targetx: INT - destination tile X
        - targety: INT - destination tile Y

    Returns: dict (parsed JSON body) on success, or None on request
    failure or an unexpected response
    """
    body = {
        "fightEvent": {
            "name": "RegularMovesFightClass",
            "type": 3,
            "actor": str(self.creature.id),
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
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(f"{env_vars['RESOLVER_URL']}/", json=body)
    except Exception as e:
        logger.error(f'Request Query KO [{e}]')
        return None
    else:
        return check_response(response, 201)


async def resolver_basic_attack(self, target):
    """
    Requests the Resolver to perform a basic attack against a target
    Creature.

    Parameters:
        - self: Mob instance (the calling Creature)
        - target: dict - must contain an 'id' key identifying the target
          Creature

    Returns: dict (parsed JSON body) on success, or None on request
    failure or an unexpected response
    """
    body = {
        "fightEvent": {
            "name": "RegularAttacksFightClass",
            "type": 0,
            "actor": str(self.creature.id),
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
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(f"{env_vars['RESOLVER_URL']}/", json=body)
    except Exception as e:
        logger.error(f'Request Query KO [{e}]')
        return None
    else:
        return check_response(response, 200)

#
# Checkers
#


def check_response(response, code):
    """
    Validates an HTTP response against an expected status code and parses
    its JSON body.

    Parameters:
        - response: httpx.Response
        - code: INT - expected HTTP status code

    Returns: dict (parsed JSON body) if response.status_code == code and a
    body is present, else None
    """
    logger.trace('HTTP response Headers:' + str(response.headers))
    logger.trace('HTTP response Code:' + str(response.status_code))
    logger.trace('HTTP response Body:' + str(response.text))

    # requests.Response is falsy on 4xx/5xx; httpx.Response has no such
    # override and is always truthy, so check explicitly instead of relying
    # on either library's boolean-conversion behaviour.
    if response is not None:
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
