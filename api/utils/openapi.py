# -*- coding: utf8 -*-

from flask import jsonify
from pydantic import ValidationError


def make_validation_error_response(e: ValidationError):
    """ flask-openapi3's validation_error_callback.

    Reshapes a pydantic ValidationError raised while parsing a route's
    body/query/path model into this API's existing error envelope, so
    routes that switch to flask-openapi3's automatic validation keep
    returning exactly what they did with their old hand-rolled
    try/except ValidationError block (400, not flask-openapi3's default
    422 + raw pydantic error JSON).
    """
    response = jsonify(
        {
            "success": False,
            "msg": "Validation and parsing error",
            "payload": e.errors(),
        }
    )
    response.status_code = 400
    return response
