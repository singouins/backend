# -*- coding: utf8 -*-

from flask_jwt_extended import decode_token

from utils.redis import r
from variables import env_vars, TOKEN_DURATION

REFRESH_TOKEN_DURATION = 30 * 24 * 60 * 60  # 30 days, in seconds


def register_access_token(username, access_token):
    """ Store an access token's jti in Redis so it can later be revoked. """
    access_jti = decode_token(access_token)["jti"]
    r.set(
        f"{env_vars['API_ENV']}:auth:access_jti:{access_jti}",
        username,
        ex=TOKEN_DURATION * 60,
        )


def register_refresh_token(username, refresh_token):
    """ Store a refresh token's jti in Redis so it can later be revoked. """
    refresh_jti = decode_token(refresh_token)["jti"]
    r.set(
        f"{env_vars['API_ENV']}:auth:refresh_jti:{refresh_jti}",
        username,
        ex=REFRESH_TOKEN_DURATION,
        )
