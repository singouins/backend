# -*- coding: utf8 -*-


from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.constants import RARITY
from mongo.models.Satchel import SatchelDocument
from mongo.utils import utcnow

from routes._decorators import exists, belongs
from utils.pa import instance_tick
from utils.redis import get_pa, consume_pa

#
# Profession.recycling specifics
#
PA_COST_RED = 0
PA_COST_BLUE = 2


#
# Routes /mypc/<uuid:creatureuuid>/action
#
# API: PUT /mypc/<uuid:creatureuuid>/action/item/catalyze/<uuid:itemuuid>
@jwt_required()
# Custom decorators
@exists.creature
@belongs.creature_out_of_instance
@exists.pa(red=PA_COST_RED, blue=PA_COST_BLUE)
@exists.item
@belongs.item_to_creature
def catalyze(creatureuuid, itemuuid):

    if g.Item.rarity == 'Legendary':
        msg = f'{g.h} ItemUUID({g.Item.id}) is already the highest rarity ({g.Item.rarity})'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": {
                    "item": g.Item.to_mongo(),
                },
            }
        ), 200

    Satchel = SatchelDocument.objects(_id=g.Creature.id).get()

    # We check the next rarity level
    rarity_index = RARITY.index(g.Item.rarity)
    next_rarity = RARITY[rarity_index + 1]

    available_shards = getattr(Satchel.shard, next_rarity.lower())
    if available_shards < 10:
        msg = f'{g.h} Not enough shard.{next_rarity.lower()} to catalyze this item.'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": {
                    "item": g.Item.to_mongo(),
                    "satchel": Satchel.to_mongo(),
                },
            }
        ), 200

    try:
        # Update Item
        g.Item.update(
            set__rarity=next_rarity,
            set__updated=utcnow()
        )

        # Update Satchel amount
        update_data = {
            f"inc__shard__{next_rarity.lower()}": -10,
            "set__updated": utcnow()
        }
        Satchel.update(**update_data)

        # We reload for up to date return
        g.Item.reload()
        Satchel.reload()
    except Exception as e:
        msg = f'{g.h} Catalyze Query KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": {
                    "item": g.Item.to_mongo(),
                    "satchel": Satchel.to_mongo(),
                },
            }
        ), 200
    else:
        # We consume the PA
        tick = instance_tick(g.Creature)
        consume_pa(creatureuuid=g.Creature.id, bluepa=PA_COST_BLUE, redpa=PA_COST_RED, tick=tick)

        msg = f'{g.h} Catalyze Query OK'
        logger.debug(msg)

        return jsonify(
            {
                "success": True,
                "msg": msg,
                "payload": {
                    "pa": get_pa(creatureuuid=g.Creature.id, tick=tick),
                    "item": g.Item.to_mongo(),
                    "satchel": Satchel.to_mongo(),
                },
            }
        ), 200
