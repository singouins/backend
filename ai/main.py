#!/usr/bin/env python3
# -*- coding: utf8 -*-

import asyncio
import json
import os
import threading

from flask import Flask, jsonify
from loguru import logger
from prometheus_client import start_http_server

from utils.redis import r
from utils.actions import creature_init, creature_kill, creature_pop, reconcile_threads
from utils.requests import resolver_generic_request_get

from variables import env_vars

# Log System imports
logger.info('[core] System imports OK')

# Create a Flask application
app = Flask(__name__)

# List to store live Creature Mob instances - a true module global so the
# Flask routes (running in their own thread) and the asyncio event loop
# (running in the main thread) can both read/mutate the same list.
threads = []


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


async def reconcile_loop(threads, interval):
    while True:
        await asyncio.sleep(interval)
        pruned = reconcile_threads(threads)
        if pruned:
            logger.warning(f'[core] Reconciliation pruned {pruned} dead Creature thread(s)')


async def main():
    # Pre-flight check for Resolver connection
    if os.environ.get("CI"):
        pass
    elif env_vars['RESOLVER_CHECK_SKIP']:
        pass
    else:
        try:
            ret = await resolver_generic_request_get(path="/check")
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
    except Exception as e:
        logger.error(f'[core] >> Redis KO [{e}]')
    else:
        logger.info('[core] >> Redis OK')

    # Starting subscription
    for path in SUB_PATHS:
        try:
            logger.trace(f'[core] Subscribe to Redis:"{path}" >>')
            await pubsub.psubscribe(path)
        except Exception as e:
            logger.error(f'[core] Subscribe to Redis:"{path}" KO [{e}]')
        else:
            logger.info(f'[core] Subscribe to Redis:"{path}" OK')

    # Start the Flask server in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000))
    flask_thread.start()

    # Start the Prometheus server
    start_prometheus_server()

    # Initialize the Threads with existing Creatures in DB
    await creature_init()

    # Periodically sweep for threads that died without going through
    # creature_kill(), so bookkeeping can't silently drift from reality
    asyncio.create_task(reconcile_loop(threads, env_vars['RECONCILE_INTERVAL']))

    # We receive the events from Redis
    async for msg in pubsub.listen():
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
                    await creature_pop(data['creature'], threads)
                elif data['action'] == 'kill':
                    creature_kill(data['creature'], threads)
                elif data['action'] == 'update':
                    # Some shit happened to a Creature - need to update thread info
                    pass
            else:
                logger.warning(f"Message unknown (data:{data})")
        except Exception as e:
            logger.error(f"[core] Listener KO on message ({msg}) [{e}]")


if __name__ == '__main__':
    asyncio.run(main())
