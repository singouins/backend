#!/usr/bin/env python3
# -*- coding: utf8 -*-

import sys
import time

from flask import jsonify, g
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_openapi3 import Info, OpenAPI
from prometheus_flask_exporter import PrometheusMetrics
from werkzeug.middleware.proxy_fix import ProxyFix

from variables import (
    env_vars,
    SEP_SECRET_KEY,
    GUNICORN_BIND,
    GUNICORN_CHDIR,
    GUNICORN_RELOAD,
    GUNICORN_THREADS,
    GUNICORN_WORKERS,
    )
from utils.gunilog import (
    InterceptHandler,
    LOG_LEVEL,
    logger,
    logging,
    StandaloneApplication,
    StubbedGunicornLogger,
    )
from utils.openapi import make_validation_error_response
from utils.redis import r

from routes.auth import auth_bp

# This service used to be the /auth blueprint mounted under the game api's
# own domain (api.domain.tld/auth); it's now a standalone service, so its
# routes are at the root (auth.domain.tld/login, /register, ...) - see
# routes/auth/__init__.py's auth_bp (no url_prefix) and auth/docs/ARCHITECTURE.md.
info = Info(title="Singouins Auth API", version="0.0.1")
security_schemes = {
    "access_token": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
    "refresh_token": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
    }
app = OpenAPI(
    __name__,
    info=info,
    security_schemes=security_schemes,
    validation_error_callback=make_validation_error_response,
    doc_prefix="/openapi",
    )
CORS(app)                         # We wrap around all the app the CORS
metrics = PrometheusMetrics(app)  # We wrap around all the app the metrics

app.register_api(auth_bp)

# Setup the ProxyFix to have the Real-IP in the logs
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Setup the Flask-JWT-Extended extension
app.config['JWT_SECRET_KEY'] = SEP_SECRET_KEY
jwt = JWTManager(app)


@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token_type = jwt_payload.get("type", "access")  # This will be 'access' or 'refresh'
    token_in_redis = r.get(f"{env_vars['API_ENV']}:auth:{token_type}_jti:{jti}")
    return token_in_redis is not None and token_in_redis.decode() == 'revoked'


@app.before_request
def before_request_time():
    g.start = time.time()


@app.after_request
def after_request_time(response):
    response.headers["X-Custom-Elapsed"] = time.time() - g.start
    return response


#
# Routes /check (k8s livenessProbe)
#
@app.route('/check', methods=['GET'])
def check():
    return jsonify(
        {
            "msg": 'UP and running',
            "success": True,
            "payload": None,
            }
        ), 200


if __name__ == '__main__':
    intercept_handler = InterceptHandler()
    logging.root.setLevel(LOG_LEVEL)

    seen = set()
    for name in [
        *logging.root.manager.loggerDict.keys(),
        "gunicorn",
        "gunicorn.access",
        "gunicorn.error",
    ]:
        if name not in seen:
            seen.add(name.split(".")[0])
            logging.getLogger(name).handlers = [intercept_handler]

    logger.configure(handlers=[{"sink": sys.stdout}])

    options = {
        "bind": GUNICORN_BIND,
        "workers": GUNICORN_WORKERS,
        "threads": GUNICORN_THREADS,
        "accesslog": "-",
        "errorlog": "-",
        "logger_class": StubbedGunicornLogger,
        "reload": GUNICORN_RELOAD,
        "chdir": GUNICORN_CHDIR
    }

    StandaloneApplication(app, options).run()
