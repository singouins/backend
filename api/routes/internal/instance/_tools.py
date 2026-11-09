# -*- coding: utf8 -*-

import datetime
import uuid

from typing import Optional

from flask import jsonify
from loguru import logger
from pydantic import BaseModel


class InternalCallSchema(BaseModel):
    """ Body of every /internal/instance/* call. Logged only, never acted upon. """
    reason: str
    by: Optional[uuid.UUID] = None
    at: datetime.datetime
    requestId: uuid.UUID


def bad_request(msg: str, payload=None):
    logger.warning(f'[Internal] {msg}')
    return jsonify(
        {
            "success": False,
            "msg": msg,
            "payload": payload,
        }
    ), 400


def member_scope(group, prefix: str):
    """
    Discord scope ('<prefix>-<id>') of a Creature's Korp or Squad membership,
    or None when it is not a member.

    CreatureKorp.id and CreatureSquad.id default to None, so an embedded
    korp/squad document does not mean a membership: only a non-None id does
    (the embedded document itself may be None). A Pending invitee is not a
    member: an invite sets the id together with rank 'Pending'. A missing
    rank counts as a member.
    """
    group_id = getattr(group, 'id', None)
    if group_id is None or getattr(group, 'rank', None) == 'Pending':
        return None
    return f'{prefix}-{group_id}'
