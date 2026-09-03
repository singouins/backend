# -*- coding: utf8 -*-

from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from loguru import logger

from utils.auth import register_access_token
from routes.auth import auth_bp
from routes.auth.schemas import AccessTokenResponse


@auth_bp.post(
    '/refresh',
    summary="Exchange a refresh token for a new access token",
    security=[{"refresh_token": []}],
    responses={200: AccessTokenResponse},
    )
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    register_access_token(identity, access_token)

    logger.trace("Refresh Token Query OK")
    return jsonify(
        {
            'access_token': access_token
        }
    ), 200
