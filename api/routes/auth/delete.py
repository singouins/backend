# -*- coding: utf8 -*-

from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from loguru import logger

from mongo.models.User import UserDocument


# API: DELETE /auth/delete
@jwt_required()
def delete():
    # The target is always the caller's own account - never take it from
    # the request body, or any authenticated user could delete any other.
    username = get_jwt_identity()

    try:
        User = UserDocument.objects(name=username).get()
    except UserDocument.DoesNotExist:
        msg = 'UserDocument Query KO (404)'
        logger.warning(msg)
        return jsonify(
            {
                "msg": msg,
            }
        ), 200

    try:
        logger.debug(f'User deletion >> (username:{username})')
        User.delete()
    except Exception as e:
        msg = f'User deletion KO (username:{username}) [{e}]'
        logger.error(msg)
        return jsonify(
            {
                "msg": msg,
            }
        ), 200
    else:
        msg = f'User deletion OK (username:{username})'
        logger.debug(msg)
        return jsonify(
            {
                "msg": msg,
            }
        ), 200
