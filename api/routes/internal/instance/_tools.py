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
