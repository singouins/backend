# -*- coding: utf8 -*-

import datetime

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.models.Satchel import SatchelDocument

from utils.decorators import (
    check_creature_exists,
    check_item_exists,
    check_user_exists,
    check_creature_owned,
    )
from utils.pa import instance_tick, pa_shortfall_colour
from utils.redis import get_pa, consume_pa
from variables import metaNames


#
# Routes /mypc/<uuid:creatureuuid>/action
#
# API: POST /mypc/<uuid:creatureuuid>/action/reload/<uuid:itemuuid>
@jwt_required()
# Custom decorators
@check_user_exists
@check_creature_exists
@check_creature_owned
@check_item_exists
def reload(creatureuuid, itemuuid):
    itemmeta = [x for x in metaNames[g.Item.metatype] if x['_id'] == g.Item.metaid][0]
    if itemmeta['pas_reload'] is None:
        msg = f'{g.h} Not reloadable'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    if g.Item.ammo == itemmeta['max_ammo']:
        msg = f"{g.h} Already loaded ({g.Item.ammo}/{itemmeta['max_ammo']})"
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # PA check (designer ruling Q15: reload costs the weapon's pas_reload in red PA, no blue).
    # Done here, not with check_creature_pa, as the cost depends on the weapon.
    # Before the Satchel read: a refusal costs no Mongo query and mutates nothing.
    cost_red = itemmeta['pas_reload']
    tick = instance_tick(g.Creature)
    if tick is None:
        # Designer ruling: outside an Instance there are no PA, nothing to check
        logger.trace(f'{g.h} not in an Instance: no PA check')
    else:
        pa = get_pa(creatureuuid=g.Creature.id, tick=tick)
        color = pa_shortfall_colour(pa['red']['pa'], pa['blue']['pa'], cost_red, 0)
        if color is not None:
            msg = f'{g.h} Not enough PA({color}) for this action'
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": pa,
                }
            ), 200

    try:
        Satchel = SatchelDocument.objects().filter(_id=g.Creature.id).get()

        # We calculate the amount of needed ammo to reload
        ownedammo = getattr(Satchel.ammo, itemmeta['caliber'])
        neededammo = itemmeta['max_ammo'] - g.Item.ammo
        details = f"(cal:{itemmeta['caliber']}, ammo:{neededammo}/{ownedammo})"

        if ownedammo < neededammo:
            msg = f"{g.h} Not enough Ammo to reload {details}"
            logger.debug(msg)
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 200
        else:
            logger.trace(f"{g.h} Enough Ammo to reload {details}")

        # We reload the weapon
        g.Item.ammo = itemmeta['max_ammo']
        g.Item.updated = datetime.datetime.utcnow()
        g.Item.save()
        # We remove the ammo from Satchel
        Satchel = SatchelDocument.objects().filter(_id=g.Creature.id)
        update_query = {
            f"inc__ammo__{itemmeta['caliber']}": -neededammo,
            "set__updated": datetime.datetime.utcnow(),
            }
        Satchel.update(**update_query)
        # We consume the PA
        consume_pa(creatureuuid=g.Creature.id, redpa=cost_red, bluepa=0, tick=tick)
    except Exception as e:
        msg = f'{g.h} Reload Query KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    else:
        msg = f'{g.h} Reload Query OK'
        logger.debug(msg)
        # None outside an Instance (no PA): the payload then carries red/blue as None
        pa = get_pa(creatureuuid=g.Creature.id, tick=tick) or {'red': None, 'blue': None}
        return jsonify(
            {
                "success": True,
                "msg": msg,
                "payload": {
                    "red": pa['red'],
                    "blue": pa['blue'],
                    "weapon": g.Item.to_mongo(),
                },
            }
        ), 200
