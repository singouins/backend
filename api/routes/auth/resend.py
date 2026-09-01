# -*- coding: utf8 -*-

from flask import jsonify
from loguru import logger
from pydantic import BaseModel, EmailStr

from mongo.models.User import UserDocument
from routes.auth import auth_bp
from routes.auth.confirmation import send_confirmation_email
from routes.auth.schemas import MessageResponse, ValidationErrorResponse

GENERIC_MSG = "If that account exists and isn't confirmed yet, a new confirmation email has been sent."  # noqa: E501


class ResendConfirmationSchema(BaseModel):
    mail: EmailStr


@auth_bp.post(
    '/resend',
    summary="Resend the account-confirmation email",
    responses={
        200: MessageResponse,
        400: ValidationErrorResponse,
        500: MessageResponse,
        },
    )
def resend(body: ResendConfirmationSchema):
    # Always return the exact same response whether or not the account
    # exists or is already confirmed - same enumeration-safety principle
    # as /auth/login (see login.py). Only the actual side effect (sending
    # a new email) differs internally.
    try:
        User = UserDocument.objects(name=body.mail).get()
    except UserDocument.DoesNotExist:
        logger.debug(f'Resend confirmation: no such user (mail:{body.mail})')
        return jsonify({"msg": GENERIC_MSG}), 200
    except Exception as e:
        msg = f'Resend confirmation KO (mail:{body.mail}) [{e}]'
        logger.error(msg)
        return jsonify({"msg": msg}), 500

    if User.active:
        logger.debug(f'Resend confirmation: already active (mail:{body.mail})')
        return jsonify({"msg": GENERIC_MSG}), 200

    if send_confirmation_email(body.mail):
        logger.debug(f'Resend confirmation OK (mail:{body.mail})')
    else:
        logger.warning(f'Resend confirmation | mail KO (mail:{body.mail})')

    return jsonify({"msg": GENERIC_MSG}), 200
