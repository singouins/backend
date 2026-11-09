# -*- coding: utf8 -*-

import json
import uuid

from flask import jsonify, request
from loguru import logger
from pydantic import ValidationError, model_validator

from mongo.models.Corpse import CorpseDocument
from mongo.models.Creature import CreatureDocument
from mongo.models.Instance import InstanceDocument
from mongo.utils import JSON_OPTIONS

from routes._decorators import internal
from routes.internal.instance._tools import InternalCallSchema, bad_request
from utils.decorators import check_is_json
from utils.redis import purge_creature_keys, r
from variables import PS_AI_CREATURE


class RemoveCallSchema(InternalCallSchema):
    """
    Body of /creature/<id>/remove: `by` is the killer, `assists` the Creatures
    that helped. `assists` is cleaned, never refused (the resolver only retries
    on 5xx, a 400 would lose the kill): duplicates are dropped (first seen
    order kept) and so is the killer, who is never his own assist.
    """
    assists: list[uuid.UUID] = []

    @model_validator(mode='after')
    def clean_assists(self):
        seen = {self.by} if self.by is not None else set()
        cleaned = []
        for assist in self.assists:
            if assist not in seen:
                seen.add(assist)
                cleaned.append(assist)
        self.assists = cleaned
        return self


def _remove_gone(h: str, call: InternalCallSchema, why: str):
    """ Idempotent answer: the monster is not in this instance, nothing changed. """
    msg = f'{h} Remove OK (result:gone)'
    logger.info(f'{msg} {why} (requestId:{call.requestId}, reason:{call.reason}, by:{call.by})')  # noqa: E501
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {"result": 'gone'},
        }
    ), 200


# API: POST /internal/instance/<string:instanceid>/creature/<string:creatureid>/remove
# Called by the fight resolver when a monster dies: it leaves the map at once
# (designer ruling Q99). Idempotent and state-based, like eject:
# - unknown Instance: 404 (final for the resolver);
# - Creature unknown or not in exactly <instanceid>: {"result": "gone"}, nothing touched;
# - a Singouin (has an account): 400, it goes through /eject;
# - otherwise the monster is removed as instance close does it: AI kill, Redis
#   keys purged, Creature deleted last. It leaves a Corpse (ruling Q105, see
#   below). No Discord notice or rewards.
# The resolver retries on 5xx only, so an internal failure is never a 200.
@internal.token
@check_is_json
def remove(instanceid, creatureid):
    # Same id and body handling as eject: malformed ids are a 400, not a routing 404
    try:
        instanceid = uuid.UUID(instanceid)
        creatureid = uuid.UUID(creatureid)
    except ValueError as e:
        return bad_request(f'Malformed id [{e}]')

    if not isinstance(request.json, dict):
        return bad_request('JSON object expected')

    try:
        call = RemoveCallSchema(**request.json)  # Validate and parse the JSON data
    except ValidationError as e:
        return bad_request('Validation and parsing error', e.errors())

    h = f'[Creature.id:{creatureid}]'

    try:
        Instance = InstanceDocument.objects(_id=instanceid).first()
        if Instance is None:
            msg = f'{h} Remove KO (Instance({instanceid}) NOTFOUND)'
            logger.warning(f'{msg} (requestId:{call.requestId}, reason:{call.reason}, by:{call.by})')  # noqa: E501
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 404

        Creature = CreatureDocument.objects(_id=creatureid).first()
        if Creature is None:
            return _remove_gone(h, call, 'Creature NOTFOUND')

        if Creature.instance is None or str(Creature.instance) != str(instanceid):
            return _remove_gone(h, call, f'Creature not in Instance({instanceid}) (instance:{Creature.instance})')  # noqa: E501

        if Creature.account is not None:
            return bad_request(f'{h} Creature has an account (Singouin): use eject')

        # Same steps and order as the instance close in utils/instance.py.
        # The AI is told first, and with r.publish() (not cput(), which only
        # logs a failure): an unpublished kill must be a 500 so the resolver
        # retries, else the AI keeps a thread on a deleted mob. Being the first
        # side effect, a failure here leaves everything untouched
        r.publish(
            PS_AI_CREATURE,
            json.dumps({
                "action": 'kill',
                "instance": Instance.to_json(json_options=JSON_OPTIONS),
                "creature": Creature.to_json(json_options=JSON_OPTIONS),
                }),
            )
        # Nothing of a dead mob may outlive it: its PA pools and actives go
        purge_creature_keys(creatureuuid=Creature.id, instanceuuid=Instance.id)
        # Every dead monster leaves a Corpse, kept until the instance closes or
        # it is skinned (ruling Q105, Lordslair 2026-10-29). It takes the
        # Creature id: a retry after a later failure saves the same document
        # again (save() on an existing _id replaces it), never a second Corpse.
        # Saved as late as possible: only a failed Creature.delete() lets a
        # retry write it again, possibly after it was skinned
        CorpseDocument(
            _id=Creature.id,
            account=None,
            gender=Creature.gender,
            instance=Instance.id,
            killer=call.by,
            level=Creature.level,
            name=Creature.name,
            race=Creature.race,
            rarity=Creature.rarity,
            x=Creature.x,
            y=Creature.y,
            ).save()
        # ALWAYS KILL CREATURE THE LAST
        Creature.delete()
    except Exception as e:
        msg = f'{h} Remove KO [{e}]'
        logger.error(f'{msg} (requestId:{call.requestId}, reason:{call.reason}, by:{call.by})')
        return jsonify(
            {
                "success": False,
                "msg": msg,
                "payload": None,
            }
        ), 500

    msg = f'{h} Remove OK (result:removed)'
    logger.info(f'{msg} Instance({instanceid}) (requestId:{call.requestId}, reason:{call.reason}, by:{call.by})')  # noqa: E501
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {"result": 'removed'},
        }
    ), 200
