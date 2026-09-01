# -*- coding: utf8 -*-

import datetime

from flask import jsonify
from flask_bcrypt import check_password_hash
from flask_jwt_extended import create_access_token, create_refresh_token
from loguru import logger
from pydantic import BaseModel

from mongo.models.User import UserDocument
from routes.auth import auth_bp
from routes.auth.schemas import MessageResponse, TokenPairResponse, ValidationErrorResponse
from utils.auth import register_access_token, register_refresh_token
from variables import TOKEN_DURATION


class LoginUserSchema(BaseModel):
    username: str
    password: str


@auth_bp.post(
    '/login',
    summary="Login and receive an access/refresh token pair",
    responses={
        200: TokenPairResponse,
        400: ValidationErrorResponse,
        401: MessageResponse,
        },
    )
def login(body: LoginUserSchema):
    # Unknown username and wrong password return the exact same response -
    # a different status/message per case would let a caller enumerate
    # valid usernames by watching which one they get back.
    def invalid_credentials():
        return jsonify({"msg": "Invalid username or password"}), 401

    try:
        User = UserDocument.objects(name=body.username).get()
    except UserDocument.DoesNotExist:
        logger.debug("UserDocument Query KO (404)")
        return invalid_credentials()

    # If password mismatch
    if not check_password_hash(User.hash, body.password):
        logger.warning("Wrong password")
        return invalid_credentials()

    # Create tokens
    access_token = create_access_token(
        identity=body.username,
        expires_delta=datetime.timedelta(minutes=TOKEN_DURATION)
    )
    refresh_token = create_refresh_token(identity=body.username)

    # Store tokens in Redis for future revocation
    register_access_token(body.username, access_token)
    register_refresh_token(body.username, refresh_token)

    # Return tokens
    logger.trace("Access Token Query OK")
    return jsonify(
        {
            'access_token': access_token,
            'refresh_token': refresh_token
        }
    ), 200
