#!/usr/bin/env python3
# -*- coding: utf8 -*-

import json
import os
import threading

from flask import Flask, jsonify
from loguru import logger
from prometheus_client import start_http_server

from utils.redis import r, redis
from utils.actions import creature_init, creature_kill, creature_pop
from utils.requests import resolver_generic_request_get

from variables import env_vars

# Log System imports
logger.info('[core] System imports OK')

# Create a Flask application
app = Flask(__name__)

# Pre-flight check for Resolver connection
if os.environ.get("CI"):
    pass
elif env_vars['RESOLVER_CHECK_SKIP']:
    pass
else:
    try:
        ret = resolver_generic_request_get(
            path="/check"
        )
    except Exception as e:
        logger.error(f"[core] >> Resolver KO ({env_vars['RESOLVER_URL']}) [{e}]")
        exit()
    else:
        if ret and ret['success'] is True:
            logger.info(f"[core] >> Resolver OK ({env_vars['RESOLVER_URL']})")
        else:
            logger.warning(f"[core] >> Resolver KO ({env_vars['RESOLVER_URL']})")

# Subscriber pattern
SUB_PATHS = [env_vars['CREATURE_PATH'], env_vars['INSTANCE_PATH']]

# Opening Redis connection
try:
    pubsub = r.pubsub()
except (redis.Redis.ConnectionError,
        redis.Redis.BusyLoadingError) as e:
    logger.error(f'[core] >> Redis KO [{e}]')
else:
    logger.info('[core] >> Redis OK')

# Starting subscription
for path in SUB_PATHS:
    try:
        logger.trace(f'[core] Subscribe to Redis:"{path}" >>')
        pubsub.psubscribe(path)
    except Exception as e:
        logger.error(f'[core] Subscribe to Redis:"{path}" KO [{e}]')
    else:
        logger.info(f'[core] Subscribe to Redis:"{path}" OK')

# Defining Flask app
app = Flask(__name__)


# Defining Flask routes
@app.route('/check', methods=['GET'])
def check_get():
    return jsonify({
        "success": True,
        "payload": {'status': 'ok'},
    }), 200


@app.route('/threads', methods=['GET'])
def threads_get():
    threads_dict = []
    for i, t in enumerate(threads):
        threads_dict.append({
            "id": t.creature.id,
            "instance": t.instance.to_mongo(),
            "creature": t.creature.to_mongo(),
        })

    return jsonify({
        "success": True,
        "payload": threads_dict,
    }), 200


# Expose metrics on /metrics
def start_prometheus_server():
    start_http_server(8000)  # Expose metrics on port 8000


if __name__ == '__main__':
    # Start the Flask server in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000))
    flask_thread.start()

    # Start the Prometheus server
    start_prometheus_server()

    # List to store threads
    threads = []

    # Initialize the Threads with existing Creatures in DB
    creature_init()

    # We receive the events from Redis
    for msg in pubsub.listen():
        # We expect something like this as message
        """
        {
          "channel": b'<ai-{creature|instance}>',
          "data": b'{
            "action": <pop|kill>,
            "creature": <CreatureDocument.to_json()>
            }',
          "pattern": b'<ai-{creature|instance}>',
          "type": "pmessage",
        }
        """

        if msg['type'] != 'pmessage':
            logger.trace(f"Message receive do not contains a pmessage ({msg})")
            continue

        # A single bad/unexpected message must not kill this loop - that
        # would silently stop all future pop/kill/update processing while
        # the Flask /check endpoint keeps reporting healthy.
        try:
            data = json.loads(msg['data'])

            if msg['channel'].decode() == env_vars['CREATURE_PATH']:
                if data['action'] == 'pop':
                    creature_pop(data['creature'], threads)
                elif data['action'] == 'kill':
                    creature_kill(data['creature'], threads)
                elif data['action'] == 'update':
                    # Some shit happened to a Creature - need to update thread info
                    pass
            else:
                logger.warning(f"Message unknown (data:{data})")
        except Exception as e:
            logger.error(f"[core] Listener KO on message ({msg}) [{e}]")
