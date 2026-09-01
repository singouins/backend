# -*- coding: utf8 -*-

from flask import jsonify
from flask_bcrypt import generate_password_hash
from loguru import logger
from pydantic import BaseModel

from mongo.models.User import UserDocument
from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse
from utils.auth import revoke_current_refresh_token
from utils.token import resolve_reset_token


class ResetPasswordSchema(BaseModel):
    token: str
    password: str


@auth_bp.post(
    '/reset-password',
    summary="Set a new password using a reset code from /auth/forgot-password",
    responses={
        200: MessageResponse,
        400: MessageResponse,
        500: MessageResponse,
        },
    )
def reset_password(body: ResetPasswordSchema):
    email = resolve_reset_token(body.token)
    if email is None:
        msg = "Reset code invalid or has expired"
        logger.warning(msg)
        return jsonify({"msg": msg}), 400

    try:
        User = UserDocument.objects(name=email).get()
    except UserDocument.DoesNotExist:
        # The token was valid but the account is gone - shouldn't normally
        # happen (tokens expire in an hour), but don't crash on it.
        msg = f'Reset password KO (mail:{email}) [user not found]'
        logger.error(msg)
        return jsonify({"msg": msg}), 400
    except Exception as e:
        msg = f'Reset password KO (mail:{email}) [{e}]'
        logger.error(msg)
        return jsonify({"msg": msg}), 500

    try:
        # flask_bcrypt.generate_password_hash returns bytes. mongoengine's
        # Document(**kwargs) constructor coerces bytes to str, but plain
        # attribute assignment on an already-fetched document does not -
        # decode explicitly rather than rely on that difference.
        User.hash = generate_password_hash(body.password, rounds=10).decode()
        User.save()
    except Exception as e:
        msg = f'Reset password KO (mail:{email}) [{e}]'
        logger.error(msg)
        return jsonify({"msg": msg}), 500

    # Password changed - a session started under the old password (e.g. by
    # whoever prompted the reset) shouldn't silently keep working.
    revoke_current_refresh_token(email)

    msg = f'Reset password OK (mail:{email})'
    logger.debug(msg)
    return jsonify({"msg": msg}), 200
