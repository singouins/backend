# -*- coding: utf8 -*-

import random

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.constants import RARITY
from mongo.models.Highscore import HighscoreDocument
from mongo.models.Profession import ProfessionDocument
from mongo.models.Resource import ResourceDocument
from mongo.models.Satchel import SatchelDocument
from mongo.utils import utcnow

from routes._decorators import belongs, exists
from routes.mypc.action.profession._tools import (
    probabilistic_binary,
    profession_gain,
    profession_scaled,
    )
from utils.pa import instance_tick
from utils.redis import consume_pa, get_pa

#
# Profession.gathering specifics
#
PA_COST_RED = 0
PA_COST_BLUE = 4
PROFESSION_NAME = 'gathering'
# How far a Resource may be gathered from, in cells on both axes (0: own cell
# only). Lordslair 2026-10-29: the same distance as skinning, for now
GATHERING_RANGE = 1


def in_gathering_range(creature, resource) -> bool:
    """ True when the Resource is within GATHERING_RANGE of the Creature. """
    # A Creature without a position has no range (x/y default to None)
    if None in (creature.x, creature.y, resource.x, resource.y):
        return False
    return (
        abs(resource.x - creature.x) <= GATHERING_RANGE
        and abs(resource.y - creature.y) <= GATHERING_RANGE
        )


#
# Routes /mypc/<uuid:creatureuuid>/action
#
# API: POST /mypc/<uuid:creatureuuid>/action/profession/gathering/<uuid:resourceuuid>
@jwt_required()
# Custom decorators
@exists.creature
@belongs.creature_in_instance
# Only checked here: the PA are consumed once the gathering is validated (see below)
@exists.pa(red=PA_COST_RED, blue=PA_COST_BLUE, consume=False)
def gathering(creatureuuid, resourceuuid):
    # Check if the resource exists
    if ResourceDocument.objects(_id=resourceuuid):
        Resource = ResourceDocument.objects(_id=resourceuuid).get()
    else:
        msg = f'{g.h} ResourceUUID({resourceuuid}) NotFound'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if str(Resource.instance) != str(g.Creature.instance):
        msg = f'{g.h} ResourceUUID({resourceuuid}) not in this instance'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if not in_gathering_range(g.Creature, Resource):
        msg = f'{g.h} ResourceUUID({resourceuuid}) not in range'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Atomic claim, before anything is credited: of two concurrent gatherers,
    # only the one whose delete removes the Resource goes on
    if ResourceDocument.objects(_id=Resource.id).delete() == 0:
        msg = f'{g.h} ResourceUUID({resourceuuid}) already gathered'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    logger.trace(f'{g.h} Resource claim OK')

    # A refusal is free, PA are spent once the action is validated, even if it
    # then fails (Lordslair + chifret 2026-10-29)
    consume_pa(
        creatureuuid=g.Creature.id,
        redpa=PA_COST_RED,
        bluepa=PA_COST_BLUE,
        tick=instance_tick(g.Creature),
        )

    Profession = ProfessionDocument.objects(_id=creatureuuid).get()

    # We calculate the total quantity
    varx = 5 - RARITY.index(Resource.rarity)  # between 0 and 5
    vary = 0                                                # between 0 and 8
    varz = probabilistic_binary(g.Creature.stats.total.m)   # between 0 and 1

    # We tune a bit vary to have a better distribution
    for _ in range(profession_scaled(Profession.gathering)):
        vary += random.randint(1, 2)

    quantity = varx + vary + varz
    logger.trace(f"{g.h} Roll for {PROFESSION_NAME}: {varx} + {vary} + {varz} == {quantity}")  # noqa: E501

    # We update the Profession score
    profession_gain(g.Creature.id, PROFESSION_NAME, Profession.gathering)

    # We set the HighScores
    highscores_update_query = {
        f'inc__profession__{PROFESSION_NAME}': 1,
        'inc__internal__ore__obtained': quantity,
        "set__updated": utcnow(),
        }
    HighscoreDocument.objects(_id=g.Creature.id).update_one(**highscores_update_query)

    # We add the resources in the Satchel
    Satchel = SatchelDocument.objects(_id=creatureuuid).get()
    Satchel.update(
        inc__resource__ore=quantity,
        set__updated=utcnow()
    )
    Satchel.reload()

    # The Resource is already gone: the claim above deleted it

    # We're done
    msg = f'{g.h} Profession ({PROFESSION_NAME}) Query OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {
                "pa": get_pa(creatureuuid=g.Creature.id, tick=instance_tick(g.Creature)),
                "resource": [{
                    "count": quantity,
                    "material": 'ore',
                    "rarity": None,
                }],
            }
        }
    ), 200
