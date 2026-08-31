# -*- coding: utf8 -*-

from pydantic import BaseModel


class MessageResponse(BaseModel):
    msg: str


class UserResponse(BaseModel):
    msg: str
    user: dict


class LoggedInAsResponse(BaseModel):
    logged_in_as: str


class AccessTokenResponse(BaseModel):
    access_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str


class ValidationErrorResponse(BaseModel):
    success: bool
    msg: str
    payload: list
