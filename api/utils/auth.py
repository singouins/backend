# -*- coding: utf8 -*-

from flask_jwt_extended import decode_token

from utils.redis import r
from variables import env_vars, TOKEN_DURATION

REFRESH_TOKEN_DURATION = 30 * 24 * 60 * 60  # 30 days, in seconds


def _current_refresh_jti_key(username):
    return f"{env_vars['API_ENV']}:auth:current_refresh_jti:{username}"


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
    # Also remember this as the user's *current* refresh jti, so logout -
    # which only ever sees the access token, never the refresh token - can
    # look it up and revoke it too, without the frontend having to send it.
    r.set(_current_refresh_jti_key(username), refresh_jti, ex=REFRESH_TOKEN_DURATION)


def revoke_access_token(jti):
    """ Mark an access token's jti as revoked, with a TTL matching how long
    it would've stayed valid anyway - so the revocation record doesn't
    outlive the token it revokes. """
    r.set(
        f"{env_vars['API_ENV']}:auth:access_jti:{jti}",
        "revoked",
        ex=TOKEN_DURATION * 60,
        )


def revoke_current_refresh_token(username):
    """ Revoke whichever refresh token was last registered for this user
    (see register_refresh_token), if any. A no-op if the user has no
    currently-tracked refresh token (e.g. it already expired). """
    refresh_jti = r.get(_current_refresh_jti_key(username))
    if refresh_jti is None:
        return
    r.set(
        f"{env_vars['API_ENV']}:auth:refresh_jti:{refresh_jti.decode()}",
        "revoked",
        ex=REFRESH_TOKEN_DURATION,
        )
