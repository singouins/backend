# -*- coding: utf8 -*-

import uuid

from flask import g, jsonify, request
from flask_jwt_extended import jwt_required
from loguru import logger
from pydantic import BaseModel, ValidationError
from random import choices, randint

from mongo.constants import CREATURE_RARITY
from mongo.models.Creature import (
    CreatureDocument,
    CreatureHP,
    CreatureSlots,
    CreatureStats,
    CreatureStatsType,
    CreatureSquad,
    CreatureKorp,
)
from mongo.models.Instance import InstanceDocument
from mongo.models.Meta import MetaMap
from mongo.utils import JSON_OPTIONS, utcnow

from routes.mypc.instance._tools import get_empty_coords
from utils.decorators import (
    check_creature_exists,
    check_is_json,
    )
from utils.discord import discord_scopes
from utils.redis import cput, qput
from variables import metaIndexed, PS_AI_CREATURE, YQ_DISCORD


class AddInstanceSchema(BaseModel):
    hardcore: bool
    fast: bool
    mapid: int
    public: bool


#
# Routes /mypc/<uuid:creatureuuid>/instance/*
#
# API: PUT /mypc/<uuid:creatureuuid>/instance
@jwt_required()
# Custom decorators
@check_is_json
@check_creature_exists
def add(creatureuuid):
    try:
        instance = AddInstanceSchema(**request.json)  # Validate and parse the JSON data
    except ValidationError as e:
        return jsonify(
            {
                "success": False,
                "msg": "Validation and parsing error",
                "payload": e.errors(),
            }
        ), 400

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

    # Check if map related to mapid exists
    try:
        Map = MetaMap.objects(_id=instance.mapid).get()
    except CreatureDocument.DoesNotExist:
        logger.warning("MetaMap Query KO (404)")
    except Exception as e:
        msg = f'{g.h} Map Query KO (mapid:{instance.mapid}) [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Create the new instance
    try:
        newInstance = InstanceDocument(
            creator=g.Creature.id,
            fast=instance.fast,
            hardcore=instance.hardcore,
            map=Map.id,
            public=instance.public,
            )
        newInstance.save()

        g.Creature.instance = newInstance.id
        g.Creature.updated = utcnow()
        g.Creature.save()
    except Exception as e:
        msg = f"{g.h} Instance Query KO [{e}]"
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Everything went well, creation DONE
    # We put the info in queue for Discord
    scopes = discord_scopes(g.Creature)
    for scope in scopes:
        # Discord Queue
        qput(YQ_DISCORD, {
            "ciphered": False,
            "payload": f':map: **{g.Creature.name}** opened a new Instance',
            "embed": None,
            "scope": scope})

    # We need to create the mobs to populate the instance
    try:
        mobs_nbr = 1
        while mobs_nbr <= 3:
            try:
                #
                raceid = randint(11, 16)
                gender = randint(0, 1)
                rarity = choices(
                    CREATURE_RARITY,
                    weights=(20, 30, 20, 10, 15, 5),
                    k=1,
                    )[0]
                x = randint(1, Map.data['width'])
                y = randint(1, Map.data['height'])

                # We grab the race wanted from metaRaces
                metaRace = metaIndexed['race'][raceid]

                newMonster = CreatureDocument(
                    _id=uuid.uuid4(),
                    gender=gender,
                    hp=CreatureHP(
                        base=metaRace['min_m'] + 100,
                        current=metaRace['min_m'] + 100,
                        max=metaRace['min_m'] + 100,
                        ),
                    instance=newInstance.id,
                    korp=CreatureKorp(),
                    name=metaRace['name'],
                    race=raceid,
                    rarity=rarity,
                    squad=CreatureSquad(),
                    slots=CreatureSlots(),
                    stats=CreatureStats(
                        spec=CreatureStatsType(),
                        race=CreatureStatsType(
                            b=metaRace['min_b'],
                            g=metaRace['min_g'],
                            m=metaRace['min_m'],
                            p=metaRace['min_p'],
                            r=metaRace['min_r'],
                            v=metaRace['min_v'],
                        ),
                        total=CreatureStatsType(
                            b=metaRace['min_b'],
                            g=metaRace['min_g'],
                            m=metaRace['min_m'],
                            p=metaRace['min_p'],
                            r=metaRace['min_r'],
                            v=metaRace['min_v'],
                        ),
                    ),
                    x=x,
                    y=y,
                )
                newMonster.save()
            except Exception as e:
                logger.error(f'{g.h} Population in Instance KO for mob #{mobs_nbr} [{e}]')
            else:
                # We send in pubsub channel for IA to spawn the Mobs
                try:
                    # AI Channel (cput serialises the dict itself)
                    cput(PS_AI_CREATURE, {
                        "action": 'pop',
                        "instance": newInstance.to_json(json_options=JSON_OPTIONS),
                        "creature": newMonster.to_json(json_options=JSON_OPTIONS),
                        })
                except Exception as e:
                    msg = f'{g.h} Publish({PS_AI_CREATURE}/pop) KO [{e}]'
                    logger.error(msg)

            mobs_nbr += 1
    except Exception as e:
        msg = f'{g.h} Instance({newInstance.id}) Population KO [{e}]'
        logger.error(msg)

    try:
        # We find an empty spot to land the Creature
        (x, y) = get_empty_coords()

        g.Creature.x = x
        g.Creature.y = y
        g.Creature.updated = utcnow()
        g.Creature.save()
    except Exception as e:
        msg = f"{g.h} Creature Query KO [{e}]"
        logger.error(msg)
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 200

    # Finally everything is done
    msg = f'{g.h} Instance({newInstance.id}) Create OK'
    logger.debug(msg)
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": newInstance.to_mongo(),
        }
    ), 201
