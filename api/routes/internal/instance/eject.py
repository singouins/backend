# -*- coding: utf8 -*-

import uuid

from flask import jsonify, request
from loguru import logger
from pydantic import ValidationError

from mongo.models.Creature import CreatureDocument
from mongo.models.Highscore import HighscoreDocument
from mongo.models.Instance import InstanceDocument
from mongo.utils import utcnow

from routes._decorators import internal
from routes.internal.instance._tools import InternalCallSchema, bad_request, member_scope
from utils.decorators import check_is_json
from utils.instance import leave_instance
from utils.redis import purge_creature_keys, qput
from variables import YQ_DISCORD


def _gone(h: str, eject: InternalCallSchema, why: str):
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


def _death_scopes(Creature) -> list:
    """
    Discord scopes told about a Singouin's death: its Korp, then its Squad,
    each only for an actual membership (see member_scope). Korp and Squad
    are checked independently.
    """
    scopes = [
        member_scope(Creature.korp, 'Korp'),
        member_scope(Creature.squad, 'Squad'),
        ]
    return [scope for scope in scopes if scope is not None]


def _count_death(h: str, Creature):
    """
    +1 general.death in the Singouin's highscores. Never raises: the eject is
    already done, a failure only loses the count.
    """
    try:
        HighscoreDocument.objects(_id=Creature.id).update_one(
            inc__general__death=1, set__updated=utcnow())
    except Exception as e:
        logger.error(f'{h} Highscore death KO [{e}]')


def _announce_death(h: str, Creature):
    """ Queues the death message for Discord. Never raises: the eject is already done. """
    try:
        for scope in _death_scopes(Creature):
            qput(YQ_DISCORD, {
                "ciphered": False,
                "payload": f':skull: **{Creature.name}** died in an Instance',
                "embed": None,
                "scope": scope})
    except Exception as e:
        logger.error(f'{h} Death announce KO [{e}]')


#
# Routes /internal/instance/*
#
# API: POST /internal/instance/<string:instanceid>/creature/<string:creatureid>/eject
# Called by the fight resolver when a Singouin dies. Idempotent and state-based:
# the creature is ejected only if it is in exactly <instanceid>; otherwise
# nothing is touched and the answer is {"result": "gone"}. The resolver retries
# on 5xx only, so an internal failure must never be a 200 with success false.
# A death (reason 'death') that actually ejects the creature ('left' or
# 'closed') is counted in its highscores (general.death) and announced on
# Discord to its Korp and Squad; 'gone' never is.
@internal.token
@check_is_json
def eject(instanceid, creatureid):
    # Ids come through <string:> converters so that malformed ones are a 400
    # (a <uuid:> converter would make them a routing 404)
    try:
        instanceid = uuid.UUID(instanceid)
        creatureid = uuid.UUID(creatureid)
    except ValueError as e:
        return bad_request(f'Malformed id [{e}]')

    # A list or scalar body would make the ** unpacking below a TypeError (HTML 500)
    if not isinstance(request.json, dict):
        return bad_request('JSON object expected')

    try:
        eject = InternalCallSchema(**request.json)  # Validate and parse the JSON data
    except ValidationError as e:
        return bad_request('Validation and parsing error', e.errors())

    h = f'[Creature.id:{creatureid}]'

    try:
        Creature = CreatureDocument.objects(_id=creatureid).first()
        if Creature is None:
            return _gone(h, eject, 'Creature NOTFOUND')

        if Creature.account is None:
            return bad_request(f'{h} Creature has no account (monster)')

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
            Creature.updated = utcnow()
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

    # Only once the eject succeeded, so a count or notification issue can
    # never change its answer, and a retry ('gone') never counts it twice
    if eject.reason == 'death' and result in ('left', 'closed'):
        _count_death(h, Creature)
        _announce_death(h, Creature)

    msg = f'{h} Eject OK (result:{result})'
    logger.info(f'{msg} Instance({instanceid}) (requestId:{eject.requestId}, reason:{eject.reason}, by:{eject.by})')  # noqa: E501
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {"result": result},
        }
    ), 200
