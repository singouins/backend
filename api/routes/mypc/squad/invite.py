# -*- coding: utf8 -*-


from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger
from mongoengine import Q

from mongo.models.Creature import CreatureDocument, CreatureSquad
from mongo.utils import JSON_OPTIONS, utcnow

from utils.decorators import (
    check_creature_exists,
    check_creature_in_squad,
    check_squad_exists,
    )
from utils.redis import cput, qput
from variables import YQ_DISCORD, env_vars

#
# Squad specifics
#
KORP_MAX_MEMBERS = 10


# API: POST ../squad/<uuid:squaduuid>/invite/<uuid:targetuuid>
@jwt_required()
# Custom decorators
@check_creature_exists
@check_squad_exists
@check_creature_in_squad
def squad_invite(creatureuuid, squaduuid, targetuuid):
    CreatureTarget = CreatureDocument.objects(_id=targetuuid).get()

    if g.Creature.squad.rank != 'Leader':
        msg = f'{g.h} PC should be the squad Leader'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    if CreatureTarget.squad.id:
        msg = f'{g.h} Already in Squad'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Squad population check
    try:
        query_members = (
            Q(squad__id=g.Squad.id)
            )
        SquadMembers = CreatureDocument.objects.filter(query_members)
    except Exception as e:
        msg = f'{g.h} Squad Query KO SquadUUID({g.Squad.id}) [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if SquadMembers.count() == KORP_MAX_MEMBERS:
        msg = f'{g.h} Squad Full ({SquadMembers.count()}/{KORP_MAX_MEMBERS})'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    try:
        CreatureTarget.squad = CreatureSquad(
            id=g.Squad.id,
            rank='Pending'
            )
        CreatureTarget.updated = utcnow()
        CreatureTarget.save()
    except Exception as e:
        msg = f'{g.h} Squad Query KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Everything went well
    # Broadcast Channel
    cput(env_vars['PS_BROADCAST'], {
        "ciphered": False,
        "payload": g.Squad.to_json(json_options=JSON_OPTIONS),
        "route": 'mypc/{id1}/squad',
        "scope": 'squad'})
    # Discord Queue
    qput(YQ_DISCORD, {
        "ciphered": False,
        "payload": (
            f':information_source: **{g.Creature.name}** '
            f'invited **{CreatureTarget.name}** in this Squad'
            ),
        "embed": None,
        "scope": f'Squad-{g.Squad.id}'})

    msg = f'{g.h} Squad invite OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": g.Squad.to_mongo(),
        }
    ), 200
