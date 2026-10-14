# -*- coding: utf8 -*-

import datetime

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.models.Creature import CreatureSlots

from utils.decorators import (
    check_creature_exists,
    check_creature_pa,
    check_item_exists,
    )
from utils.pa import instance_tick
from utils.redis import r, get_pa

#
# Inventory.unequip specifics
#
PA_COST_RED = 0
PA_COST_BLUE = 0


#
# Routes /mypc/<uuid:creatureuuid>/inventory/*
#
# API: POST /mypc/<uuid:creatureuuid>/inventory/item/<uuid:itemuuid>/unequip/<string:type>/<string:slotname> # noqa
@jwt_required()
# Custom decorators
@check_creature_exists
@check_creature_pa(red=PA_COST_RED, blue=PA_COST_BLUE)
@check_item_exists
def unequip(creatureuuid, type, slotname, itemuuid):
    # Path parameter check: an attribute name that is not a slot (validate,
    # _data, ...) passes the setattr below, then breaks save() with a 500
    if slotname not in CreatureSlots._fields:
        msg = f"{g.h} Unequip KO (slotname:{slotname} unknown)"
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 400

    try:
        if slotname == 'righthand':
            if g.Creature.slots.righthand.id == itemuuid:
                if g.Creature.slots.righthand == g.Creature.slots.lefthand:
                    # The weapon equipped takes both hands
                    g.Creature.slots.righthand = None
                    g.Creature.slots.lefthand = None
                else:
                    g.Creature.slots.righthand = None
        elif slotname == 'lefthand':
            if g.Creature.slots.lefthand.id == itemuuid:
                if g.Creature.slots.righthand == g.Creature.slots.lefthand:
                    # The weapon equipped takes both hands
                    g.Creature.slots.righthand = None
                    g.Creature.slots.lefthand = None
                else:
                    g.Creature.slots.lefthand = None
        else:
            setattr(g.Creature.slots, slotname, None)
    except Exception as e:
        msg = f'{g.h} Unequip KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    else:
        g.Creature.updated = datetime.datetime.utcnow()
        g.Creature.save()

    # We send in pubsub channel for WS
    try:
        r.publish(
            'ws-broadcast',
            jsonify({
                "ciphered": False,
                "payload": g.Creature.to_mongo(),
                "route": "mypc/{id1}/inventory/item/{id2}/unequip/{id3}/{id4}",
                "scope": {
                    "id": None,
                    "instance_id": g.Creature.instance,
                    "scope": 'broadcast',
                    },
                }).get_data(as_text=True),
            )
    except Exception as e:
        msg = (f'{g.h} Equip Queue KO [{e}]')
        logger.error(msg)

    msg = f'{g.h} Unequip OK'
    logger.debug(msg)
    # None outside an Instance (no PA): the payload then carries red/blue as None
    pa = get_pa(creatureuuid=creatureuuid, tick=instance_tick(g.Creature))
    pa = pa or {'red': None, 'blue': None}
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {
                "red": pa['red'],
                "blue": pa['blue'],
                "creature": g.Creature.to_mongo(),
            },
        }
    ), 200
