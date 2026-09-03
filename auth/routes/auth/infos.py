# -*- coding: utf8 -*-

from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from loguru import logger

from routes.auth import auth_bp
from routes.auth.schemas import LoggedInAsResponse


@auth_bp.get(
    '/infos',
    summary="Get the logged-in user's identity",
    security=[{"access_token": []}],
    responses={200: LoggedInAsResponse},
    )
@jwt_required()
def infos():
    msg = "User Query OK"
    logger.trace(msg)
    # Access the identity of the current user with get_jwt_identity
    return jsonify(
        logged_in_as=get_jwt_identity(),
    ), 200
