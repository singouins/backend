# -*- coding: utf8 -*-

import uuid

from flask import jsonify
from flask_bcrypt import generate_password_hash
from loguru import logger
from pydantic import BaseModel

from utils.mail import send
from utils.token import generate_confirmation_token
from mongo.models.User import UserDocument, UserDiscord
from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse, ValidationErrorResponse
from variables import (
    API_URL,
    DATA_PATH,
    DISCORD_URL,
    )


class RegisterUserSchema(BaseModel):
    mail: str
    password: str


@auth_bp.post(
    '/register',
    summary="Register a new user and send a confirmation email",
    responses={
        200: MessageResponse,
        201: MessageResponse,
        400: ValidationErrorResponse,
        409: MessageResponse,
        },
    )
def register(body: RegisterUserSchema):
    # Check User existence
    try:
        User = UserDocument.objects(name=body.mail).get()
    except UserDocument.DoesNotExist:
        # We can create the User
        pass
    else:
        # We return an error (duplicate user)
        msg = f"User already exists (mail:{body.mail})"
        logger.debug(msg)
        return jsonify(
            {
                "msg": msg,
                "user": User.to_mongo().to_dict(),
            }
        ), 409

    try:
        newUser = UserDocument(
            _id=uuid.uuid3(uuid.NAMESPACE_DNS, body.mail),
            discord=UserDiscord(),
            hash=generate_password_hash(body.password, rounds=10),
            name=body.mail,
        )
        newUser.save()
    except Exception as e:
        msg = f'User Creation KO (mail:{body.mail}) [{e}]'
        logger.error(msg)

    # User created, we send email
    subject = '[🐒&🐖] Bienvenue chez le Singouins !'
    token = generate_confirmation_token(body.mail)
    url = f'{API_URL}/auth/confirm/{token}'
    email_body = open(f"{DATA_PATH}/registered.html", "r").read()

    if send(
        body.mail,
        subject,
        email_body.format(
            urllogo='[INSERT LOGO HERE]',
            urlconfirm=url,
            urldiscord=DISCORD_URL
            )
    ):
        msg = "User successfully added | mail OK"
        logger.debug(msg)
        return jsonify(
            {
                "msg": msg,
                "user": newUser.to_mongo().to_dict(),
            }
        ), 201
    else:
        msg = "User successfully added | mail KO"
        logger.warning(msg)
        return jsonify(
            {
                "msg": msg,
                "user": newUser.to_mongo().to_dict(),
            }
        ), 200
