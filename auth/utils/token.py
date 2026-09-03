# -*- coding: utf8 -*-

import secrets

from utils.redis import r
from variables import env_vars

CONFIRMATION_TOKEN_DURATION = 3600  # 1 hour, in seconds
RESET_TOKEN_DURATION = 3600  # 1 hour, in seconds


def _confirmation_token_key(token):
    return f"{env_vars['API_ENV']}:auth:confirm_token:{token}"


def _current_confirmation_token_key(email):
    return f"{env_vars['API_ENV']}:auth:current_confirm_token:{email}"


def generate_confirmation_token(email):
    """ Generate a Redis-backed confirmation token for `email`, valid for
    CONFIRMATION_TOKEN_DURATION seconds. Also stored under a per-email
    lookup key, so a caller who only knows the email (tests, support
    tooling) can find the current pending token without needing the
    emailed link itself. """
    token = secrets.token_urlsafe(32)
    r.set(_confirmation_token_key(token), email, ex=CONFIRMATION_TOKEN_DURATION)
    r.set(_current_confirmation_token_key(email), token, ex=CONFIRMATION_TOKEN_DURATION)
    return token


def confirm_token(token):
    """ Resolve a confirmation token to the email it was issued for, or
    None if it's invalid/unknown/expired (Redis expiring the key IS the
    expiration check - no separate max-age logic needed). """
    email = r.get(_confirmation_token_key(token))
    if email is None:
        return None
    return email.decode()


def _reset_token_key(token):
    return f"{env_vars['API_ENV']}:auth:reset_token:{token}"


def _current_reset_token_key(email):
    return f"{env_vars['API_ENV']}:auth:current_reset_token:{email}"


def generate_reset_token(email):
    """ Generate a Redis-backed password-reset token for `email`, valid for
    RESET_TOKEN_DURATION seconds. Also stored under a per-email lookup key
    (see generate_confirmation_token). """
    token = secrets.token_urlsafe(32)
    r.set(_reset_token_key(token), email, ex=RESET_TOKEN_DURATION)
    r.set(_current_reset_token_key(email), token, ex=RESET_TOKEN_DURATION)
    return token


def resolve_reset_token(token):
    """ Resolve a password-reset token to the email it was issued for, and
    consume it - unlike a confirmation token, a reset token must not be
    replayable, so a second attempt with the same token must fail even
    within its TTL. Returns None if invalid/unknown/expired/already used. """
    key = _reset_token_key(token)
    email = r.get(key)
    if email is None:
        return None
    r.delete(key)
    return email.decode()
