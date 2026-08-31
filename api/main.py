#!/usr/bin/env python3
# -*- coding: utf8 -*-

import sys
import time

from flask import jsonify, g
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_openapi3 import Info, OpenAPI
from flask_uuid import FlaskUUID
from flask_swagger_ui import get_swaggerui_blueprint
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
import routes.log
import routes.map
import routes.meta
import routes.mypc
import routes.mypc.action
import routes.mypc.action.item
import routes.mypc.action.profession
import routes.mypc.actives
import routes.mypc.events
import routes.mypc.highscores
import routes.mypc.item
import routes.mypc.instance
import routes.mypc.inventory
import routes.mypc.korp
import routes.mypc.pa
import routes.mypc.squad
import routes.mypc.view
import routes.pc

# /auth is piloting flask-openapi3 (auto-generated OpenAPI doc, served at
# /openapi, from the pydantic models already living next to each route) -
# the rest of the app is still on the legacy static/swagger.yaml + plain
# add_url_rule below. See api/docs/ARCHITECTURE.md.
info = Info(title="Singouins API", version="0.0.1")
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
FlaskUUID(app)                    # We wrap around all the app the UUID control
metrics = PrometheusMetrics(app)  # We wrap around all the app the metrics

# Setup the flask_swagger_ui extension (covers everything except /auth,
# which now documents itself - see api/static/swagger.yaml)
SWAGGERUI_BLUEPRINT = get_swaggerui_blueprint(
    '/swagger',
    '/static/swagger.yaml',
    config={'app_name': "Singouins API"}
)
app.register_blueprint(SWAGGERUI_BLUEPRINT, url_prefix='/swagger')
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


#
# Routes /meta
#
app.add_url_rule('/meta/item/<string:metatype>', methods=['GET'], view_func=routes.meta.meta_get_one)  # noqa: E501
#
# Routes: /pc
#
app.add_url_rule('/pc/<uuid:creatureuuid>', methods=['GET'], view_func=routes.pc.pc_get_one)
app.add_url_rule('/pc/<uuid:creatureuuid>/event', methods=['GET'], view_func=routes.pc.pc_event_get_all)  # noqa: E501
app.add_url_rule('/pc/<uuid:creatureuuid>/item', methods=['GET'], view_func=routes.pc.pc_item_get_all)  # noqa: E501
#
# Routes: /mypc
#
app.add_url_rule('/mypc', methods=['POST'], view_func=routes.mypc.mypc_add)
app.add_url_rule('/mypc', methods=['GET'], view_func=routes.mypc.mypc_get_all)
app.add_url_rule('/mypc/<uuid:creatureuuid>', methods=['DELETE'], view_func=routes.mypc.mypc_del)
# Routes: /action
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/resolver', methods=['POST'], view_func=routes.mypc.action.resolver)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/reload/<uuid:itemuuid>', methods=['POST'], view_func=routes.mypc.action.reload)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/unload/<uuid:itemuuid>', methods=['POST'], view_func=routes.mypc.action.unload)  # noqa: E501
# Routes: /action/item
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/item/catalyze/<uuid:itemuuid>', methods=['PUT'], view_func=routes.mypc.action.item.catalyze)  # noqa: E501
# Routes: /action/profession
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/profession/gathering/<uuid:resourceuuid>', methods=['POST'], view_func=routes.mypc.action.profession.gathering)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/profession/recycling/<uuid:itemuuid>', methods=['POST'], view_func=routes.mypc.action.profession.recycling)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/profession/skinning/<uuid:resourceuuid>', methods=['POST'], view_func=routes.mypc.action.profession.skinning)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/profession/tanning', methods=['POST'], view_func=routes.mypc.action.profession.tanning)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/action/profession/tracking', methods=['POST'], view_func=routes.mypc.action.profession.tracking)  # noqa: E501
# Routes: /actives
app.add_url_rule('/mypc/<uuid:creatureuuid>/actives/<string:actives_type>', methods=['GET'], view_func=routes.mypc.actives.actives_get)  # noqa: E501
# Routes: /events
app.add_url_rule('/mypc/<uuid:creatureuuid>/event', methods=['GET'], view_func=routes.mypc.events.mypc_event_get_all)  # noqa: E501
# Routes: /highscores
app.add_url_rule('/mypc/<uuid:creatureuuid>/highscores', methods=['GET'], view_func=routes.mypc.highscores.highscores_get)  # noqa: E501
# Routes: /instance
app.add_url_rule('/mypc/<uuid:creatureuuid>/instance', methods=['PUT'], view_func=routes.mypc.instance.add)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/instance/<uuid:instanceuuid>', methods=['GET'], view_func=routes.mypc.instance.instance_get)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/instance/<uuid:instanceuuid>/join', methods=['POST'], view_func=routes.mypc.instance.join)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/instance/<uuid:instanceuuid>/leave', methods=['POST'], view_func=routes.mypc.instance.leave)  # noqa: E501
# Routes: /inventory/item
app.add_url_rule('/mypc/<uuid:creatureuuid>/inventory/item/<uuid:itemuuid>/equip/<string:type>/<string:slotname>', methods=['POST'], view_func=routes.mypc.inventory.equip)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/inventory/item/<uuid:itemuuid>/offset/<int:offsetx>/<int:offsety>', methods=['POST'], view_func=routes.mypc.inventory.offset)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/inventory/item/<uuid:itemuuid>/offset', methods=['DELETE'], view_func=routes.mypc.inventory.offset)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/inventory/item/<uuid:itemuuid>/unequip/<string:type>/<string:slotname>', methods=['POST'], view_func=routes.mypc.inventory.unequip)  # noqa: E501
# Routes: /item
app.add_url_rule('/mypc/<uuid:creatureuuid>/item', methods=['GET'], view_func=routes.mypc.item.item_get)  # noqa: E501
# Routes: /korp
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp', methods=['POST'], view_func=routes.mypc.korp.korp_create)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>', methods=['GET'], view_func=routes.mypc.korp.korp_get)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>', methods=['DELETE'], view_func=routes.mypc.korp.korp_delete)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>/invite/<uuid:targetuuid>', methods=['POST'], view_func=routes.mypc.korp.korp_invite)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>/kick/<uuid:targetuuid>', methods=['POST'], view_func=routes.mypc.korp.korp_kick)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>/accept', methods=['POST'], view_func=routes.mypc.korp.korp_accept)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>/leave', methods=['POST'], view_func=routes.mypc.korp.korp_leave)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/korp/<uuid:korpuuid>/decline', methods=['POST'], view_func=routes.mypc.korp.korp_decline)  # noqa: E501
# Routes: /pa
app.add_url_rule('/mypc/<uuid:creatureuuid>/pa', methods=['GET'], view_func=routes.mypc.pa.pa_get)
# Routes: /squad
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad', methods=['POST'], view_func=routes.mypc.squad.squad_create)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>', methods=['GET'], view_func=routes.mypc.squad.squad_get)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>', methods=['DELETE'], view_func=routes.mypc.squad.squad_delete)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>/invite/<uuid:targetuuid>', methods=['POST'], view_func=routes.mypc.squad.squad_invite)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>/kick/<uuid:targetuuid>', methods=['POST'], view_func=routes.mypc.squad.squad_kick)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>/accept', methods=['POST'], view_func=routes.mypc.squad.squad_accept)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>/leave', methods=['POST'], view_func=routes.mypc.squad.squad_leave)  # noqa: E501
app.add_url_rule('/mypc/<uuid:creatureuuid>/squad/<uuid:squaduuid>/decline', methods=['POST'], view_func=routes.mypc.squad.squad_decline)  # noqa: E501
# Routes: /view
app.add_url_rule('/mypc/<uuid:creatureuuid>/view', methods=['GET'], view_func=routes.mypc.view.view_get)  # noqa: E501
#
# Routes: /map
#
app.add_url_rule('/map/<int:map_id>', methods=['GET'], view_func=routes.map.map_get)
#
# Routes /log
#
app.add_url_rule('/log', methods=['POST'], view_func=routes.log.front)

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
