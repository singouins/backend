# -*- coding: utf8 -*-


from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.models.Creature import CreatureKorp
from mongo.utils import JSON_OPTIONS, utcnow

from utils.decorators import (
    check_creature_exists,
    check_creature_in_korp,
    check_korp_exists,
    )
from utils.redis import cput, qput
from variables import YQ_DISCORD, env_vars


# API: POST /mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>/accept
@jwt_required()
# Custom decorators
@check_creature_exists
@check_korp_exists
@check_creature_in_korp
def korp_accept(creatureuuid, korpuuid):
    if g.Creature.korp.rank != 'Pending':
        msg = f'{g.h} Pending is required'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    try:
        g.Creature.korp = CreatureKorp(
            id=g.Korp.id,
            rank='Member',
        )
        g.Creature.updated = utcnow()
        g.Creature.save()
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
            f'joined this Korp (**{g.Korp.name}**)'
            ),
        "embed": None,
        "scope": f'Korp-{g.Korp.id}'})

    msg = f'{g.h} Korp accept OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": g.Korp.to_mongo(),
        }
    ), 200
