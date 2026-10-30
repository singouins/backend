# -*- coding: utf8 -*-


from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.constants import RARITY
from mongo.models.Creature import CreatureDocument, CreatureSlots
from mongo.models.Highscore import HighscoreDocument
from mongo.models.Profession import ProfessionDocument
from mongo.models.Satchel import SatchelDocument
from mongo.utils import utcnow

from routes._decorators import exists, belongs
from routes.mypc.action.profession._tools import (
    probabilistic_binary,
    profession_gain,
    profession_scaled,
    )
from utils.item_lock import delete_locked_item, lock_item, unlock_item
from utils.pa import instance_tick
from utils.redis import consume_pa, get_pa

#
# Profession.recycling specifics
#
PA_COST_RED = 0
PA_COST_BLUE = 2
PROFESSION_NAME = 'recycling'


def is_equipped(creature, item) -> bool:
    """ True when the Item sits in one of the Creature's slots. """
    slots = creature.slots
    if slots is None:
        return False
    for slotname in CreatureSlots._fields:
        slot = getattr(slots, slotname, None)
        if slot is not None and slot.id is not None and str(slot.id) == str(item.id):
            return True
    return False


#
# Routes /mypc/<uuid:creatureuuid>/action
#
# API: POST /mypc/<uuid:creatureuuid>/action/profession/recycling/<uuid:itemuuid>
@jwt_required()
# Custom decorators
@exists.creature
@belongs.creature_out_of_instance
# Only checked here: the PA are consumed once the Item checks passed (see below)
@exists.pa(red=PA_COST_RED, blue=PA_COST_BLUE, consume=False)
@exists.item
@belongs.item_to_creature
def recycling(creatureuuid, itemuuid):
    # Held until the Item is deleted: of two recyclings, or of an equip and a
    # recycling, of this Item, only one goes on (see utils/item_lock.py)
    token = lock_item(g.Item.id)
    if token is None:
        msg = f'{g.h} ItemUUID({itemuuid}) busy or already recycled'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # An equipped Item must be unequipped first: recycling deletes it, which
    # would leave its slot pointing at nothing. The slots are read again, now
    # that the Item is locked: an equip that ended meanwhile is seen here
    Creature = CreatureDocument.objects(_id=g.Creature.id).get()
    if is_equipped(Creature, g.Item):
        unlock_item(g.Item.id, token)
        msg = f'{g.h} ItemUUID({itemuuid}) is equipped'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Deleted before anything is credited, by the lock holder only
    if not delete_locked_item(g.Item.id, token):
        msg = f'{g.h} ItemUUID({itemuuid}) already recycled'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    logger.trace(f'{g.h} Item destroy OK')

    # A refusal is free, PA are spent once the action is validated, even if it
    # then fails (Lordslair + chifret 2026-10-29)
    consume_pa(
        creatureuuid=g.Creature.id,
        redpa=PA_COST_RED,
        bluepa=PA_COST_BLUE,
        tick=instance_tick(g.Creature),
        )

    Profession = ProfessionDocument.objects(_id=creatureuuid).get()

    varx = 5 - RARITY.index(g.Item.rarity)   # between 0 and 5
    vary = profession_scaled(Profession.recycling)         # between 0 and 4
    varz = probabilistic_binary(g.Creature.stats.total.b)  # between 0 and 1

    # We roll the dice and calculate the total quantity
    shards_qty = varx + vary + varz
    logger.trace(f"{g.h} Roll for {PROFESSION_NAME}: {varx} + {vary} + {varz} == {shards_qty}")

    # We set the HighScores
    highscores_update_query = {
        f'inc__profession__{PROFESSION_NAME}': 1,
        'inc__internal__item__recycled': 1,
        'inc__internal__shard__obtained': shards_qty,
        "set__updated": utcnow(),
        }
    HighscoreDocument.objects(_id=g.Creature.id).update_one(**highscores_update_query)

    # We add the resources in the Satchel
    Satchel = SatchelDocument.objects(_id=creatureuuid).get()
    satchel_update_query = {
        f"inc__shard__{g.Item.rarity.lower()}": shards_qty,
        "set__updated": utcnow(),
        }
    Satchel.update(**satchel_update_query)
    Satchel.reload()

    # We update the Profession score
    profession_gain(g.Creature.id, PROFESSION_NAME, Profession.recycling)

    # We're done
    msg = f'{g.h} Profession ({PROFESSION_NAME}) Query OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {
                "pa": get_pa(creatureuuid=g.Creature.id, tick=instance_tick(g.Creature)),
                "resource": [
                    {
                        "count": shards_qty,
                        "material": 'shards',
                        "rarity": g.Item.rarity,
                        },
                    ],
                "inventory": "HARDCODED_VALUE",
                "satchel": Satchel.to_mongo(),
            }
        }
    ), 200
