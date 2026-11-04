# -*- coding: utf8 -*-


from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.models.Creature import CreatureDocument, CreatureSquad
from mongo.models.Squad import SquadDocument
from mongo.utils import JSON_OPTIONS, utcnow

from utils.decorators import (
    check_creature_exists,
    check_creature_in_squad,
    check_squad_exists,
    )
from utils.redis import cput, qput
from variables import YQ_DISCORD, env_vars


# API: DELETE ../squad/<uuid:squaduuid>
@jwt_required()
# Custom decorators
@check_creature_exists
@check_squad_exists
@check_creature_in_squad
def squad_delete(creatureuuid, squaduuid):
    if g.Creature.squad.rank != 'Leader':
        msg = f'{g.h} Not the squad Leader ({g.Creature.squad.rank})'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if CreatureDocument.objects(squad__id=g.Creature.squad.id).count() > 1:
        msg = f'{g.h} Squad not empty'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    try:
        SquadDocument.objects(_id=g.Squad.id).delete()
        g.Creature.squad = CreatureSquad()
        g.Creature.updated = utcnow()
        g.Creature.save()
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
            f'deleted this Squad'
            ),
        "embed": None,
        "scope": f'Squad-{g.Squad.id}'})

    msg = f'{g.h} Squad delete OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": None,
        }
    ), 200
