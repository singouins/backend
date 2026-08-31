# -*- coding: utf8 -*-

from flask import jsonify
from flask_jwt_extended import get_jwt, jwt_required
from loguru import logger

from utils.redis import r
from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse

from variables import env_vars


@auth_bp.delete(
    '/logout',
    summary="Revoke the caller's current access token",
    security=[{"access_token": []}],
    responses={200: MessageResponse},
    )
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    try:
        r.set(f"{env_vars['API_ENV']}:auth:access_jti:{jti}", "revoked")  # Mark token as revoked
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
