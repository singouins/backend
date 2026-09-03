# -*- coding: utf8 -*-

from flask import jsonify
from loguru import logger
from pydantic import BaseModel

from utils.token import confirm_token
from mongo.models.User import UserDocument
from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse


class ConfirmTokenPath(BaseModel):
    token: str


@auth_bp.get(
    '/confirm/<string:token>',
    summary="Confirm a newly registered user's email",
    responses={200: MessageResponse},
    )
def confirm(path: ConfirmTokenPath):
    username = confirm_token(path.token)
    if not username:
        msg = "Confirmation link invalid or has expired"
        logger.warning(msg)
        return jsonify({"msg": msg}), 200

    User = UserDocument.objects(name=username).first()
    if User is None:
        msg = f'User confirmation KO (username:{username}) [user not found]'
        logger.error(msg)
        return jsonify({"msg": msg}), 200

    try:
        User.active = True
        User.save()
    except Exception as e:
        msg = f'User confirmation KO (username:{username}) [{e}]'
        logger.error(msg)
        return jsonify({"msg": msg}), 200

    msg = f'User confirmation OK (username:{username})'
    logger.trace(msg)
    return jsonify({"msg": msg}), 200
