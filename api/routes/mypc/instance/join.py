# -*- coding: utf8 -*-

import datetime

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from routes.mypc.instance._tools import get_empty_coords
from utils.decorators import (
    check_creature_exists,
    check_instance_exists,
    )
from utils.discord import discord_scopes
from utils.redis import qput
from variables import YQ_DISCORD


# API: POST /mypc/<uuid:creatureuuid>/instance/<uuid:instanceuuid>/join
@jwt_required()
# Custom decorators
@check_creature_exists
@check_instance_exists
def join(creatureuuid, instanceuuid):
    if g.Creature.instance:
        msg = f'{g.h} already in Instance({g.Creature.instance})'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if g.Creature.id in g.Instance.leavers:
        msg = f'{g.h} Instance({g.Instance.id}) Join KO: left before, no re-entry'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # We add the Creature into the instance
    try:
        # We find an empty spot to land the Creature
        (x, y) = get_empty_coords()

        g.Creature.x = x
        g.Creature.y = y
        g.Creature.instance = g.Instance.id
        g.Creature.updated = datetime.datetime.utcnow()
        g.Creature.save()
    except Exception as e:
        msg = f'{g.h} Instance({g.Instance.id}) Query KO [{e}]'
        logger.error(msg)
        return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 200
    else:
        # We put the info in queue for Discord
        scopes = discord_scopes(g.Creature)
        for scope in scopes:
            # Discord Queue
            qput(YQ_DISCORD, {
                "ciphered": False,
                "payload": f':map: **{g.Creature.name}** joined a new Instance',
                "embed": None,
                "scope": scope})
        # Everything went well
        msg = f'{g.h} Instance({g.Instance.id}) Join OK'
        logger.debug(msg)
        return jsonify(
            {
                "success": True,
                "msg": msg,
                "payload": g.Creature.to_mongo(),
            }
        ), 200
