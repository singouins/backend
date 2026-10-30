# -*- coding: utf8 -*-

import random

from flask import g, jsonify
from flask_jwt_extended import jwt_required
from loguru import logger

from mongo.constants import CREATURE_RARITY
from mongo.models.Corpse import CorpseDocument
from mongo.models.Creature import CreatureDocument
from mongo.models.Highscore import HighscoreDocument
from mongo.models.Profession import ProfessionDocument
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
# Profession.skinning specifics
#
PA_COST_RED = 0
PA_COST_BLUE = 2
PROFESSION_NAME = 'skinning'


def can_skin(skinner, corpse) -> bool:
    """
    Who may skin a Corpse (ruling Q105, Lordslair 2026-10-29): its killer and
    the killer's Squad.

    - the killer always may;
    - no killer (corpse.killer None): nobody may (Q105 point 5, ruled
      Lordslair 2026-10-29: "personne");
    - a killer without a Squad (or only invited, rank 'Pending'): the killer
      alone (Q105 point 5, ruled Lordslair 2026-10-29: "lui seul");
    - otherwise a member of the killer's Squad, read now, at skinning time.
      A Pending invitee is not a member (ruling 2026-10-10).
    An unknown killer Creature (deleted since) leaves nobody but itself.
    """
    if corpse.killer is None:
        return False
    if str(skinner.id) == str(corpse.killer):
        return True

    killer = CreatureDocument.objects(_id=corpse.killer).first()
    if killer is None:
        return False

    killer_squad = getattr(killer.squad, 'id', None)
    if killer_squad is None or getattr(killer.squad, 'rank', None) == 'Pending':
        return False

    skinner_squad = getattr(skinner.squad, 'id', None)
    return (
        skinner_squad is not None
        and str(skinner_squad) == str(killer_squad)
        and getattr(skinner.squad, 'rank', None) != 'Pending'
        )


#
# Routes /mypc/<uuid:creatureuuid>/action
#
# API: POST ../profession/skinning/<uuid:resourceuuid>
@jwt_required()
# Custom decorators
@exists.creature
@belongs.creature_in_instance
# Only checked here: the PA are consumed once the Corpse is claimed (see below)
@exists.pa(red=PA_COST_RED, blue=PA_COST_BLUE, consume=False)
def skinning(creatureuuid, resourceuuid):

    # Check if the corpse exists
    try:
        Corpse = CorpseDocument.objects(_id=resourceuuid).get()
    except CorpseDocument.DoesNotExist:
        msg = f'{g.h} CorpseUUID({resourceuuid}) NotFound'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # x/y default to None on both documents: without a position there is no
    # range to check, so it is a refusal (the distance below would raise)
    positions = (Corpse.x, Corpse.y, g.Creature.x, g.Creature.y)
    if any(position is None for position in positions):
        msg = f'{g.h} CorpseUUID({resourceuuid}) range unknown (no position)'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if abs(Corpse.x - g.Creature.x) > 1 or abs(Corpse.y - g.Creature.y) > 1:
        msg = f'{g.h} CorpseUUID({resourceuuid}) not in range'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if str(Corpse.instance) != str(g.Creature.instance):
        msg = f'{g.h} CorpseUUID({resourceuuid}) not in this instance'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    if not can_skin(g.Creature, Corpse):
        msg = f'{g.h} CorpseUUID({resourceuuid}) not skinnable by this creature'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Atomic claim, before anything is credited: of two concurrent skinners,
    # only the one whose delete removes the Corpse goes on
    if CorpseDocument.objects(_id=Corpse.id).delete() == 0:
        msg = f'{g.h} CorpseUUID({resourceuuid}) already skinned'
        logger.warning(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200
    logger.trace(f'{g.h} Corpse claim OK')

    # A refusal is free, PA are only spent on a done action (Lordslair
    # 2026-10-29): consumed here, by the skinner who claimed the Corpse
    consume_pa(
        creatureuuid=g.Creature.id,
        redpa=PA_COST_RED,
        bluepa=PA_COST_BLUE,
        tick=instance_tick(g.Creature),
        )

    Profession = ProfessionDocument.objects(_id=creatureuuid).get()

    # We update the Profession score
    profession_gain(g.Creature.id, PROFESSION_NAME, Profession.skinning)

    # To check what's going to be created
    resource_skinned = {'skin': 0, 'meat': 0}

    for resource in resource_skinned:
        # We calculate the total quantity
        varx = CREATURE_RARITY.index(Corpse.rarity)   # between 0 and 5
        vary = 0                                               # between 0 and 4
        varz = probabilistic_binary(g.Creature.stats.total.r)  # between 0 and 1

        # We tune a bit vary to have a better distribution
        for _ in range(profession_scaled(Profession.skinning)):
            vary += random.randint(1, 2)

        resource_skinned[resource] = varx + vary + varz
        logger.trace(f"{g.h} Roll for {PROFESSION_NAME}/{resource}: {varx} + {vary} + {varz} == {resource_skinned[resource]}")  # noqa: E501

    # We set the HighScores
    highscores_update_query = {
        f'inc__profession__{PROFESSION_NAME}': 1,
        'inc__internal__meat__obtained': resource_skinned['meat'],
        'inc__internal__skin__obtained': resource_skinned['skin'],
        "set__updated": utcnow(),
        }
    HighscoreDocument.objects(_id=g.Creature.id).update_one(**highscores_update_query)

    # We add the resources in the Satchel
    satchel_update_query = {
        "inc__resource__meat": resource_skinned['meat'],
        "inc__resource__skin": resource_skinned['skin'],
        "set__updated": utcnow(),
        }
    SatchelDocument.objects(_id=creatureuuid).update_one(**satchel_update_query)

    # Little snippet to check amount of resources // slots
    # slots_used = 0
    # satchel = r.json().get(f'satchels:{g.Creature.id}')
    # for resource_data in satchel['resources'].values():
    #    for resource in resource_data.values():
    #        slots_used += resource

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
                        "count": resource_skinned['meat'],
                        "material": 'meat',
                        "rarity": None,
                        },
                    {
                        "count": resource_skinned['skin'],
                        "material": 'skin',
                        "rarity": None,
                        },
                    ],
                "inventory": "HARDCODED_VALUE",
            }
        }
    ), 200
