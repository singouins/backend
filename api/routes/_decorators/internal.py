# -*- coding: utf8 -*-

import functools
import hmac

from flask import jsonify, request
from loguru import logger

# Read as a module attribute at call time (never `from variables import ...`):
# the token can then be swapped under test, and a missing one is a runtime
# 503 rather than an import error. Only flask/functools/hmac/loguru here, so
# this module stays importable without Mongo (see tests/test_00_internal_token.py).
import variables


def token(func):
    """
    Decorator guarding a service-to-service route with the shared internal token.

    Expects `Authorization: Bearer <SEP_INTERNAL_TOKEN>`:
    - 503 when no token is configured (internal API disabled);
    - 401 when the header is missing or not a Bearer scheme with a token;
    - 403 when the token does not match.
    The token value is never logged.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        expected = variables.SEP_INTERNAL_TOKEN
        if not expected:
            msg = 'Internal API disabled (no token configured)'
            logger.warning(f'[Internal] {msg}')
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 503

        authorization = request.headers.get('Authorization', '')
        scheme, _, provided = authorization.partition(' ')
        if scheme != 'Bearer' or not provided:
            msg = 'Missing or malformed Authorization header (Bearer token expected)'
            logger.warning(f'[Internal] {msg}')
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 401

        # Compared as bytes: compare_digest raises TypeError on non-ASCII str,
        # and Werkzeug decodes headers as latin-1, so that is reachable from the wire
        if not hmac.compare_digest(provided.encode('utf-8'), expected.encode('utf-8')):
            msg = 'Invalid internal token'
            logger.warning(f'[Internal] {msg}')
            return jsonify(
                {
                    "success": False,
                    "msg": msg,
                    "payload": None,
                }
            ), 403

        return func(*args, **kwargs)

    return wrapper
