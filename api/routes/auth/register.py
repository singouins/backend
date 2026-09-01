# -*- coding: utf8 -*-

import uuid

from flask import jsonify
from flask_bcrypt import generate_password_hash
from loguru import logger
from pydantic import BaseModel, EmailStr

from mongo.models.User import UserDocument, UserDiscord
from routes.auth import auth_bp
from routes.auth.confirmation import send_confirmation_email
from routes.auth.schemas import MessageResponse, UserResponse, ValidationErrorResponse


class RegisterUserSchema(BaseModel):
    mail: EmailStr
    password: str


def _public_user(user):
    """ user.to_mongo().to_dict(), minus the password hash. """
    doc = user.to_mongo().to_dict()
    doc.pop('hash', None)
    return doc


@auth_bp.post(
    '/register',
    summary="Register a new user and send a confirmation email",
    responses={
        200: UserResponse,
        201: UserResponse,
        400: ValidationErrorResponse,
        409: UserResponse,
        500: MessageResponse,
        },
    )
def register(body: RegisterUserSchema):
    # Check User existence
    try:
        User = UserDocument.objects(name=body.mail).get()
    except UserDocument.DoesNotExist:
        # We can create the User
        pass
    except Exception as e:
        msg = f'User existence check KO (mail:{body.mail}) [{e}]'
        logger.error(msg)
        return jsonify({"msg": msg}), 500
    else:
        # We return an error (duplicate user)
        msg = f"User already exists (mail:{body.mail})"
        logger.debug(msg)
        return jsonify(
            {
                "msg": msg,
                "user": _public_user(User),
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
        # Never fall through to the "success" path below on a failed save -
        # newUser was never persisted, so there's nothing to email a
        # confirmation link for or report back as created.
        return jsonify({"msg": msg}), 500

    # User created, we send email
    if send_confirmation_email(body.mail):
        msg = "User successfully added | mail OK"
        logger.debug(msg)
        return jsonify(
            {
                "msg": msg,
                "user": _public_user(newUser),
            }
        ), 201
    else:
        msg = "User successfully added | mail KO"
        logger.warning(msg)
        return jsonify(
            {
                "msg": msg,
                "user": _public_user(newUser),
            }
        ), 200
