# -*- coding: utf8 -*-

import datetime

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.models.Creature import CreatureSlot

from utils.decorators import (
    check_creature_exists,
    check_item_exists,
    )
from utils.pa import equip_cost, instance_tick, pa_shortfall_colour
from utils.redis import r, get_pa, consume_pa
from variables import metaIndexed, metaNames


#
# Routes /mypc/<uuid:creatureuuid>/inventory/*
#
# API: POST /mypc/<uuid:creatureuuid>/inventory/item/<uuid:itemuuid>/equip/<string:type>/<string:slotname> # noqa
@jwt_required()
# Custom decorators
@check_creature_exists
@check_item_exists
def equip(creatureuuid, type, slotname, itemuuid):
    itemmeta = [x for x in metaNames[type] if x['_id'] == g.Item.metaid][0]
    sizex, sizey = itemmeta['size'].split("x")

    # PA check (designer rulings Q102 + Q108: red PA by item size, no blue).
    # Done here, not with check_creature_pa, as the cost depends on the item.
    cost = equip_cost(itemmeta['size'])
    if cost is None:
        msg = f"{g.h} No equip PA cost for this item size (size:{itemmeta['size']})"
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    tick = instance_tick(g.Creature)
    if tick is None:
        # Designer ruling: outside an Instance there are no PA, nothing to check
        logger.trace(f'{g.h} not in an Instance: no PA check')
    else:
        pa = get_pa(creatureuuid=g.Creature.id, tick=tick)
        color = pa_shortfall_colour(pa['red']['pa'], pa['blue']['pa'], cost['red'], cost['blue'])
        if color is not None:
            msg = f'{g.h} Not enough PA({color}) for this action'
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": pa,
                }
            ), 200

    # Pre-requisite checks
    for carac in ['m', 'r', 'g', 'v', 'p', 'b']:
        needed = itemmeta[f'min_{carac}']
        stat = getattr(g.Creature.stats.total, carac)
        if needed > stat:
            msg = f"{g.h} {carac.upper()} prequisites KO (min_{carac}:{needed} > {carac}:{stat})"
            logger.warning(msg)
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 200

    try:
        logger.trace(f"{g.h} Equip Query >> {slotname}")
        if slotname == 'holster':
            if int(sizex) * int(sizey) <= 4:
                # It fits inside the holster
                g.Creature.slots.holster = CreatureSlot(
                    id=g.Item.id,
                    metaid=g.Item.metaid,
                    metatype=g.Item.metatype,
                    )
            else:
                msg = f"{g.h} Item does not fit in holster (size:{itemmeta['size']})"
                return jsonify(
                    {
                        "success": False,
                        "msg": msg,
                        "payload": None,
                    }
                ), 200
        elif slotname == 'righthand':
            if g.Creature.slots.righthand:
                # Something is already equipped in RH
                equippedMeta = metaIndexed['weapon'][g.Creature.slots.righthand.metaid]
                # We equip a 1H weapon
                if int(sizex) * int(sizey) <= 6:
                    if equippedMeta['onehanded'] is True:
                        # A 1H weapons is in RH : we replace
                        g.Creature.slots.righthand = CreatureSlot(
                            id=g.Item.id,
                            metaid=g.Item.metaid,
                            metatype=g.Item.metatype,
                            )
                    if equippedMeta['onehanded'] is False:
                        # A 2H weapons is in RH & LH
                        # We replace RH and clean LH
                        g.Creature.slots.righthand = CreatureSlot(
                            id=g.Item.id,
                            metaid=g.Item.metaid,
                            metatype=g.Item.metatype,
                            )
                        g.Creature.slots.lefthand = None
                # We equip a 2H weapon
                if int(sizex) * int(sizey) > 6:
                    # It is a 2H weapon: it fits inside the RH & LH
                    g.Creature.slots.righthand = CreatureSlot(
                        id=g.Item.id,
                        metaid=g.Item.metaid,
                        metatype=g.Item.metatype,
                        )
                    g.Creature.slots.lefthand = CreatureSlot(
                        id=g.Item.id,
                        metaid=g.Item.metaid,
                        metatype=g.Item.metatype,
                        )
            else:
                # Nothing in RH
                # We equip a 1H weapon
                if int(sizex) * int(sizey) <= 6:
                    g.Creature.slots.righthand = CreatureSlot(
                        id=g.Item.id,
                        metaid=g.Item.metaid,
                        metatype=g.Item.metatype,
                        )
                # We equip a 2H weapon
                if int(sizex) * int(sizey) > 6:
                    # It is a 2H weapon: it fits inside the RH & LH
                    g.Creature.slots.righthand = CreatureSlot(
                        id=g.Item.id,
                        metaid=g.Item.metaid,
                        metatype=g.Item.metatype,
                        )
                    g.Creature.slots.lefthand = CreatureSlot(
                        id=g.Item.id,
                        metaid=g.Item.metaid,
                        metatype=g.Item.metatype,
                        )
        elif slotname == 'lefthand':
            if int(sizex) * int(sizey) <= 4:
                # It fits inside the left hand
                g.Creature.slots.lefthand = CreatureSlot(
                    id=g.Item.id,
                    metaid=g.Item.metaid,
                    metatype=g.Item.metatype,
                    )
            else:
                msg = f"{g.h} Item does not fit in left hand (size:{itemmeta['size']})"
                logger.trace(msg)
                return jsonify(
                    {
                        "success": False,
                        "msg": msg,
                        "payload": None,
                    }
                ), 200
        else:
            setattr(
                g.Creature.slots,
                slotname,
                CreatureSlot(
                    id=g.Item.id,
                    metaid=g.Item.metaid,
                    metatype=g.Item.metatype,
                    )
                )
    except Exception as e:
        msg = (f'{g.h} Equip Query KO [{e}]')
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

    # Here everything should be OK with the equip
    # We consume the PA
    consume_pa(creatureuuid=creatureuuid, redpa=cost['red'], bluepa=cost['blue'], tick=tick)

    # We put the info in queue for ws
    try:
        r.publish(
            'ws-broadcast',
            jsonify({
                "ciphered": False,
                "payload": g.Creature.to_mongo(),
                "route": "mypc/{id1}/inventory/item/{id2}/equip/{id3}/{id4}",
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

    # JOB IS DONE
    msg = f'{g.h} Equip Query OK'
    logger.debug(msg)
    # None outside an Instance (no PA): the payload then carries red/blue as None
    pa = get_pa(creatureuuid=creatureuuid, tick=tick) or {'red': None, 'blue': None}
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
