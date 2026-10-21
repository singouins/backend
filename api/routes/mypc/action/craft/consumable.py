# -*- coding: utf8 -*-

import datetime

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.models.Satchel import SatchelDocument

from routes._decorators import exists, belongs
from utils.pa import instance_tick
from utils.redis import get_pa, consume_pa

#
# Craft.consumable specifics
#
PA_COST_RED = 0
PA_COST_BLUE = 2
# Design ruling Q78: consumables meta 1 (standard heal) is plain currency,
# never crafted. Crafted ones go to the Satchel.consumable field below.
STANDARD_CONSUMABLE_METAID = 1
CRAFTED_CONSUMABLES = {
    2: 'fast',
    3: 'long',
    }
CRAFT_COUNT = 1
# Cost of the 'craft_potion' recipe (mongo/data/metas/recipes.json,
# component.wallet). The api has no in-memory access to the recipe metas
# (variables.metaNames holds armor/weapon/race only), so it is mirrored here:
# keep both in sync. 'currency' is banana: every race is a singouin for now.
RECIPE_CURRENCY = 25
RECIPE_SHARD_BROKEN = 1


#
# Routes /mypc/<uuid:creatureuuid>/action
#
# API: POST /mypc/<uuid:creatureuuid>/action/craft/consumable/<int:metaid>
@jwt_required()
# Custom decorators
@exists.creature
@belongs.creature_out_of_instance
@exists.pa(red=PA_COST_RED, blue=PA_COST_BLUE)
def consumable(creatureuuid, metaid):
    # Path parameter checks: before any Satchel write or PA spend
    if metaid == STANDARD_CONSUMABLE_METAID:
        msg = f'{g.h} Craft KO (consumable:{metaid} is plain currency, never crafted)'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 400

    kind = CRAFTED_CONSUMABLES.get(metaid)
    if kind is None:
        msg = f'{g.h} Craft KO (consumable:{metaid} unknown)'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 400

    try:
        # One conditional update: the cost is checked and paid atomically,
        # so two concurrent crafts cannot both spend the same resources.
        # $inc creates consumable.<kind> on satchels that predate the field.
        updated = SatchelDocument.objects(
            _id=g.Creature.id,
            currency__banana__gte=RECIPE_CURRENCY,
            shard__broken__gte=RECIPE_SHARD_BROKEN,
        ).update_one(
            **{
                "inc__currency__banana": -RECIPE_CURRENCY,
                "inc__shard__broken": -RECIPE_SHARD_BROKEN,
                f"inc__consumable__{kind}": CRAFT_COUNT,
                "set__updated": datetime.datetime.utcnow(),
            }
        )
        Satchel = SatchelDocument.objects(_id=g.Creature.id).first()
    except Exception as e:
        msg = f'{g.h} Craft Query KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if Satchel is None:
        msg = f'{g.h} Craft KO (Satchel NOTFOUND)'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 404

    if updated == 0:
        msg = (f'{g.h} Not enough currency.banana ({RECIPE_CURRENCY})'
               f' or shard.broken ({RECIPE_SHARD_BROKEN}) to craft.')
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": {
                    "satchel": Satchel.to_mongo(),
                },
            }
        ), 200

    # We consume the PA
    tick = instance_tick(g.Creature)
    consume_pa(creatureuuid=g.Creature.id, bluepa=PA_COST_BLUE, redpa=PA_COST_RED, tick=tick)

    msg = f'{g.h} Craft Query OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {
                "pa": get_pa(creatureuuid=g.Creature.id, tick=tick),
                "satchel": Satchel.to_mongo(),
            },
        }
    ), 200
