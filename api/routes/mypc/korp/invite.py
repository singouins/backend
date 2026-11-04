# -*- coding: utf8 -*-


from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger
from mongoengine import Q

from mongo.models.Creature import CreatureDocument, CreatureKorp
from mongo.utils import JSON_OPTIONS, utcnow

from utils.decorators import (
    check_creature_exists,
    check_creature_in_korp,
    check_korp_exists,
    )
from utils.redis import cput, qput
from variables import YQ_DISCORD, env_vars

#
# Korp specifics
#
KORP_MAX_MEMBERS = 10


# API: POST ../korp/<uuid:korpuuid>/invite/<uuid:targetuuid>
@jwt_required()
# Custom decorators
@check_creature_exists
@check_korp_exists
@check_creature_in_korp
def korp_invite(creatureuuid, korpuuid, targetuuid):
    CreatureTarget = CreatureDocument.objects(_id=targetuuid).get()

    if g.Creature.korp.rank != 'Leader':
        msg = f'{g.h} PC should be the korp Leader'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    if CreatureTarget.korp.id:
        msg = f'{g.h} Already in Korp'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Korp population check
    try:
        query_members = (
            Q(korp__id=g.Korp.id)
            )
        KorpMembers = CreatureDocument.objects.filter(query_members)
    except Exception as e:
        msg = f'{g.h} Korp Query KO KorpUUID({g.Korp.id}) [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if KorpMembers.count() == KORP_MAX_MEMBERS:
        msg = f'{g.h} Korp Full ({KorpMembers.count()}/{KORP_MAX_MEMBERS})'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    try:
        CreatureTarget.korp = CreatureKorp(
            id=g.Korp.id,
            rank='Pending'
            )
        CreatureTarget.updated = utcnow()
        CreatureTarget.save()
    except Exception as e:
        msg = f'{g.h} Korp Query KO [{e}]'
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
        "payload": g.Korp.to_json(json_options=JSON_OPTIONS),
        "route": 'mypc/{id1}/korp',
        "scope": 'korp'})
    # Discord Queue
    qput(YQ_DISCORD, {
        "ciphered": False,
        "payload": (
            f':information_source: **{g.Creature.name}** '
            f'invited **{CreatureTarget.name}** in this Korp (**{g.Korp.name}**)'
            ),
        "embed": None,
        "scope": f'Korp-{g.Korp.id}'})

    msg = f'{g.h} Korp invite OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": g.Korp.to_mongo(),
        }
    ), 200
