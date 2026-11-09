# -*- coding: utf8 -*-

import json
import uuid

from flask import jsonify, request
from loguru import logger
from pydantic import ValidationError, model_validator

from mongo.models.Corpse import CorpseDocument
from mongo.models.Creature import CreatureDocument
from mongo.models.Highscore import HighscoreDocument
from mongo.models.Instance import InstanceDocument
from mongo.utils import JSON_OPTIONS, utcnow

from routes._decorators import internal
from routes.internal.instance._tools import InternalCallSchema, bad_request
from utils.decorators import check_is_json
from utils.redis import purge_creature_keys, r
from utils.xp import apply_xp, xp_gain
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


# A Singouin's (level, xp) is written only if it is still what was read: on a
# conflict (another kill resolved at the same time), it is read again and the
# gain recomputed, at most this many times
XP_WRITE_ATTEMPTS = 5


def _xp_participants(call: RemoveCallSchema) -> list:
    """
    Who takes part in the kill: the killer (`by`, when set), then the assists.
    RemoveCallSchema already dropped the duplicates and the killer from the
    assists, so nobody is counted twice. The killer's Squad members are
    expected in the assists, sent by the resolver: they are not looked up here.
    """
    killer = [call.by] if call.by is not None else []
    return killer + call.assists


def _grant_xp_to(h: str, Singouin, Creature, players: int):
    """
    One Singouin's XP for the kill, level-ups included (utils/xp.py). The
    gain depends on the Singouin's level, and a level-up rewrites both level
    and xp: so it is a read, compute, then a write conditioned on the
    (level, xp) read. Another kill landing in between makes the write match
    nothing: the Singouin is read again and the gain recomputed.
    """
    for _ in range(XP_WRITE_ATTEMPTS):
        gain = xp_gain(Singouin.level, Creature.level, Creature.rarity, players)
        if gain <= 0:
            logger.info(f'{h} XP skipped for Creature({Singouin.id}) (gain:0, level:{Singouin.level})')  # noqa: E501
            return
        level, xp = apply_xp(Singouin.level, Singouin.xp, gain)
        written = CreatureDocument.objects(
            _id=Singouin.id, level=Singouin.level, xp=Singouin.xp,
            ).update_one(set__level=level, set__xp=xp)
        if written:
            up = f', level up:{Singouin.level}->{level}' if level > Singouin.level else ''
            logger.info(f'{h} XP OK for Creature({Singouin.id}) (+{gain}{up})')
            return
        Singouin = CreatureDocument.objects(_id=Singouin.id).only('_id', 'level', 'xp').first()
        if Singouin is None:
            logger.warning(f'{h} XP skipped (Creature deleted meanwhile)')
            return
    logger.error(f'{h} XP KO for Creature({Singouin.id}) (still conflicting after {XP_WRITE_ATTEMPTS} attempts)')  # noqa: E501


def _grant_xp(h: str, Creature, call: RemoveCallSchema):
    """
    Gives the XP of a monster's death to the participants who are Singouins
    (an account): a monster or an unknown id gets nothing and is not counted
    in the group size. Each Singouin's gain is computed from its own level
    (utils/xp.py: level gap, rarity, group bonus, cap), and may level it up.
    Never raises: the remove is already done, and a failure must not turn it
    into a 500 (a retry would answer 'gone' anyway). A failure loses the XP,
    for that Singouin only.
    """
    try:
        participants = _xp_participants(call)
        if not participants:
            logger.info(f'{h} XP skipped (no participant)')
            return
        players = list(CreatureDocument.objects(
            _id__in=participants, account__ne=None).only('_id', 'level', 'xp'))
    except Exception as e:
        logger.error(f'{h} XP KO [{e}]')
        return
    if not players:
        logger.info(f'{h} XP skipped (no Singouin among {len(participants)} participant(s))')  # noqa: E501
        return
    for Singouin in players:
        try:
            _grant_xp_to(h, Singouin, Creature, len(players))
        except Exception as e:
            logger.error(f'{h} XP KO for Creature({Singouin.id}) [{e}]')


def _count_kill(h: str, call: RemoveCallSchema):
    """
    Highscores of the kill: +1 general.kill for the killer (`by`), +1
    general.assist for each assist. Only Singouins have a Highscore, so a
    monster or an unknown id matches nothing. Same rules as _grant_xp: called
    once the monster is gone (never counted twice), never raises (a failure
    loses the count). The kill and the assists fail independently.
    """
    if call.by is not None:
        try:
            counted = HighscoreDocument.objects(_id=call.by).update_one(
                inc__general__kill=1, set__updated=utcnow())
            logger.debug(f'{h} Highscore kill OK (counted:{counted})')
        except Exception as e:
            logger.error(f'{h} Highscore kill KO [{e}]')
    if call.assists:
        try:
            counted = HighscoreDocument.objects(_id__in=call.assists).update(
                inc__general__assist=1, set__updated=utcnow())
            logger.debug(f'{h} Highscore assist OK (counted:{counted}/{len(call.assists)})')
        except Exception as e:
            logger.error(f'{h} Highscore assist KO [{e}]')


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
#   below), then its XP goes to the killer and the assists, level-ups
#   included (_grant_xp, utils/xp.py), and their kill / assist highscores
#   go up (_count_kill).
#   No Discord notice.
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

    # XP and highscores once the monster is gone, never before: a retry then
    # answers 'gone' and never comes back here, so a kill is never paid twice
    _grant_xp(h, Creature, call)
    _count_kill(h, call)

    msg = f'{h} Remove OK (result:removed)'
    logger.info(f'{msg} Instance({instanceid}) (requestId:{call.requestId}, reason:{call.reason}, by:{call.by})')  # noqa: E501
    return jsonify(
        {
            "success": True,
            "msg": msg,
            "payload": {"result": 'removed'},
        }
    ), 200
