# -*- coding: utf8 -*-

import datetime
import uuid

from typing import Optional

from flask import jsonify, request
from loguru import logger
from pydantic import BaseModel, ValidationError

from mongo.models.Creature import CreatureDocument
from mongo.models.Instance import InstanceDocument

from routes._decorators import internal
from utils.decorators import check_is_json
from utils.instance import leave_instance
from utils.redis import purge_creature_keys


class EjectSchema(BaseModel):
    reason: str
    by: Optional[uuid.UUID] = None
    at: datetime.datetime
    requestId: uuid.UUID


def _bad_request(msg: str, payload=None):
    logger.warning(f'[Internal] {msg}')
    return jsonify(
        {
            "success": False,
            "msg": msg,
            "payload": payload,
        }
    ), 400


def _gone(h: str, eject: EjectSchema, why: str):
    """ Idempotent answer: the creature is not in this instance, nothing changed. """
    msg = f'{h} Eject OK (result:gone)'
    logger.info(f'{msg} {why} (requestId:{eject.requestId}, reason:{eject.reason}, by:{eject.by})')  # noqa: E501
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {"result": 'gone'},
        }
    ), 200


#
# Routes /internal/instance/*
#
# API: POST /internal/instance/<string:instanceid>/creature/<string:creatureid>/eject
# Called by the fight resolver when a Singouin dies. Idempotent and state-based:
# the creature is ejected only if it is in exactly <instanceid>; otherwise
# nothing is touched and the answer is {"result": "gone"}. The resolver retries
# on 5xx only, so an internal failure must never be a 200 with success false.
@internal.token
@check_is_json
def eject(instanceid, creatureid):
    # Ids come through <string:> converters so that malformed ones are a 400
    # (a <uuid:> converter would make them a routing 404)
    try:
        instanceid = uuid.UUID(instanceid)
        creatureid = uuid.UUID(creatureid)
    except ValueError as e:
        return _bad_request(f'Malformed id [{e}]')

    # A list or scalar body would make the ** unpacking below a TypeError (HTML 500)
    if not isinstance(request.json, dict):
        return _bad_request('JSON object expected')

    try:
        eject = EjectSchema(**request.json)  # Validate and parse the JSON data
    except ValidationError as e:
        return _bad_request('Validation and parsing error', e.errors())

    h = f'[Creature.id:{creatureid}]'

    try:
        Creature = CreatureDocument.objects(_id=creatureid).first()
        if Creature is None:
            return _gone(h, eject, 'Creature NOTFOUND')

        if Creature.account is None:
            return _bad_request(f'{h} Creature has no account (monster)')

        if Creature.instance is None or str(Creature.instance) != str(instanceid):
            return _gone(h, eject, f'Creature not in Instance({instanceid}) (instance:{Creature.instance})')  # noqa: E501

        Instance = InstanceDocument.objects(_id=instanceid).first()
        if Instance is None:
            # Dangling reference: the Instance is gone but the Creature still
            # points at it. Detach and purge, as leave_instance() would
            logger.warning(f'{h} Instance({instanceid}) NOTFOUND, detaching the Creature')
            Creature.instance = None
            Creature.x = None
            Creature.y = None
            Creature.updated = datetime.datetime.utcnow()
            Creature.save()
            purge_creature_keys(creatureuuid=Creature.id, instanceuuid=instanceid)
            result = 'left'
        else:
            result = leave_instance(Creature, Instance)
    except Exception as e:
        msg = f'{h} Eject KO [{e}]'
        logger.error(f'{msg} (requestId:{eject.requestId}, reason:{eject.reason}, by:{eject.by})')
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 500

    msg = f'{h} Eject OK (result:{result})'
    logger.info(f'{msg} Instance({instanceid}) (requestId:{eject.requestId}, reason:{eject.reason}, by:{eject.by})')  # noqa: E501
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {"result": result},
        }
    ), 200
