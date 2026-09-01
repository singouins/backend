# -*- coding: utf8 -*-

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from loguru import logger

from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse
from utils.auth import revoke_access_token, revoke_current_refresh_token


@auth_bp.delete(
    '/logout',
    summary="Revoke the caller's current access token and refresh token",
    security=[{"access_token": []}],
    responses={200: MessageResponse},
    )
@jwt_required()
def logout():
    identity = get_jwt_identity()
    jti = get_jwt()["jti"]
    try:
        revoke_access_token(jti)
        revoke_current_refresh_token(identity)
    except Exception as e:
        msg = f'JTI Revokation KO [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "msg": msg,
            }
        ), 200
    else:
        msg = 'JTI Revokation OK'
        logger.trace(msg)
        return jsonify(
            {
                "msg": msg,
            }
        ), 200
