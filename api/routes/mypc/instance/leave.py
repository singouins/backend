# -*- coding: utf8 -*-

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from utils.decorators import (
    check_creature_exists,
    check_creature_in_instance,
    )
from utils.discord import discord_scopes
from utils.instance import leave_instance
from utils.redis import qput
from variables import YQ_DISCORD


# API: POST /mypc/<uuid:creatureuuid>/instance/<uuid:instanceuuid>/leave
@jwt_required()
# Custom decorators
@check_creature_exists
@check_creature_in_instance
def leave(creatureuuid, instanceuuid):

    try:
        outcome = leave_instance(g.Creature, g.Instance)
    except Exception as e:
        msg = f'{g.h} Instance({g.Instance.id}) leave KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    else:
        if outcome == 'closed':
            payload = f':map: **{g.Creature.name}** closed an Instance'
            msg = f'{g.h} Instance({g.Instance.id}) leave OK'
        else:
            payload = f':map: **{g.Creature.name}** left an Instance'
            msg = f'{g.h} Instance({g.Instance.id}) Leave OK'

        # We put the info in queue for Discord
        scopes = discord_scopes(g.Creature)
        for scope in scopes:
            # Discord Queue
            qput(YQ_DISCORD, {
                "ciphered": False,
                "payload": payload,
                "embed": None,
                "scope": scope})

        logger.debug(msg)
        return jsonify(
            {
                "success": True,
                "msg": msg,
                "payload": g.Creature.to_mongo(),
            }
        ), 200
