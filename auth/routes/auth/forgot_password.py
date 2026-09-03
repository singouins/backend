# -*- coding: utf8 -*-

from string import Template

from flask import jsonify
from loguru import logger
from pydantic import BaseModel, EmailStr

from mongo.models.User import UserDocument
from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse, ValidationErrorResponse
from utils.mail import send
from utils.token import generate_reset_token
from variables import DATA_PATH, DISCORD_URL

GENERIC_MSG = "If that account exists, a password reset code has been sent by email."


class ForgotPasswordSchema(BaseModel):
    mail: EmailStr


def _send_reset_password_email(mail):
    """ Generate a fresh password-reset token for `mail` and email it as an
    opaque code - not a clickable link - for the user to paste into the app
    alongside their new password (see reset_password.py). Always
    generates/stores the token regardless of whether the email actually
    goes out; returns whatever utils.mail.send() returns (True/False). """
    subject = '[🐒&🐖] Réinitialisation de mot de passe'
    token = generate_reset_token(mail)
    with open(f"{DATA_PATH}/forgot_password.html", "r") as f:
        email_body = f.read()

    email_body = Template(email_body).substitute(
        urllogo='[INSERT LOGO HERE]',
        token=token,
        urldiscord=DISCORD_URL,
        )

    return send(mail, subject, email_body)


@auth_bp.post(
    '/forgot-password',
    summary="Request a password-reset code by email",
    responses={
        200: MessageResponse,
        400: ValidationErrorResponse,
        500: MessageResponse,
        },
    )
def forgot_password(body: ForgotPasswordSchema):
    # Same enumeration-safety principle as /auth/login and /auth/resend -
    # the response never reveals whether the account exists.
    try:
        UserDocument.objects(name=body.mail).get()
    except UserDocument.DoesNotExist:
        logger.debug(f'Forgot password: no such user (mail:{body.mail})')
        return jsonify({"msg": GENERIC_MSG}), 200
    except Exception as e:
        msg = f'Forgot password KO (mail:{body.mail}) [{e}]'
        logger.error(msg)
        return jsonify({"msg": msg}), 500

    if _send_reset_password_email(body.mail):
        logger.debug(f'Forgot password: reset email sent (mail:{body.mail})')
    else:
        logger.warning(f'Forgot password: reset email KO (mail:{body.mail})')

    return jsonify({"msg": GENERIC_MSG}), 200
