# -*- coding: utf8 -*-

import json

from loguru import logger
from mongoengine import Q

from bestiaire import (
    Salamander,
    Fungus
    )
from mongo.models.Creature import CreatureDocument
from utils.redis import r

from variables import (
    env_vars,
    THREAD_COUNT_FUNGUS,
    THREAD_COUNT_SALAMANDER,
    THREAD_COUNT_TOTAL,
    )


def creature_init():
    try:
        # We Initialize with ALL the existing NPC Creatures in an instance
        query = (Q(instance__exists=True) & Q(race__gt=10))
        Creatures = CreatureDocument.objects(query)
    except CreatureDocument.DoesNotExist:
        logger.debug("[Initialization] Skipped (no Creatures fetched)")
    except Exception as e:
        logger.error(f"[Initialization] Creatures Query KO [{e}]")
    else:
        logger.trace("[Initialization] Creatures Query OK")
        logger.trace("Creature Loading >>")
        for Creature in Creatures:
            # Like a lazy ass, we publish it into the channel
            # to be treated in the listen() code
            try:
                r.publish(
                    env_vars['CREATURE_PATH'],
                    json.dumps({
                        "action": 'pop',
                        "creature": Creature.to_json(),
                    })
                )
            except Exception as e:
                logger.error(f"Creature publish KO | [{Creature.id}] {Creature.name} [{e}]")
            else:
                logger.trace(f"Creature publish OK | [{Creature.id}] {Creature.name}")
        logger.debug("Creature Loading OK")


def creature_pop(creature: str, threads: list):
    # We have to pop a new creature somewhere
    creature = json.loads(creature)
    logger.trace(f'pmessage["data"]: {creature}')
    name = f"[{creature['_id']}] {creature['name']}"
    # We check that it exists in MongoDB
    try:
        Creature = CreatureDocument.objects(_id=creature['_id']).get()
    except CreatureDocument.DoesNotExist:
        logger.warning(f'Creature pop KO | {name} (NotFound in MongoDB)')
        return False

    try:
        logger.trace(f"We pop a {creature['name']}")
        THREAD_COUNT_TOTAL.inc()           # Increment the total thread count
        if Creature.race in [11, 12, 13, 14]:
            t = Salamander(creatureuuid=Creature.id)
            THREAD_COUNT_SALAMANDER.inc()  # Increment the Salamander thread count
        elif Creature.race in [15, 16]:
            t = Fungus(creatureuuid=Creature.id)
            THREAD_COUNT_FUNGUS.inc()      # Increment the Fungus thread count
        else:
            THREAD_COUNT_TOTAL.dec()       # No thread was actually created
            logger.warning(f'Creature pop KO | {name} (Unhandled race:{Creature.race})')
            return False

        t.start()
        threads.append(t)
    except Exception as e:
        logger.error(f'Creature pop KO | {name} [{e}]')
        return False
    else:
        logger.debug(f'Creature pop OK | {name}')
        return True


def creature_kill(creature: str, threads: list):
    # We have to kill an existing creature somewhere
    creature = json.loads(creature)
    try:
        killed = False
        name = f"[{creature['_id']}] {creature['name']}"
        for i, t in enumerate(threads):
            if str(t.creature.id) == creature['_id']:
                # We got the dead Creature
                logger.trace(f'Creature to kill found: {name}')
                t.creature.hp.current = 0

                THREAD_COUNT_TOTAL.dec()           # Decrement total thread count when done
                if t.creature.race in [11, 12, 13, 14]:
                    THREAD_COUNT_SALAMANDER.dec()  # Decrement Salamander thread count when done
                elif t.creature.race in [15, 16]:
                    THREAD_COUNT_FUNGUS.dec()      # Decrement Fungus thread count when done

                threads.remove(t)
                killed = True
    except Exception as e:
        logger.error(f"Creature kill KO | {name} [{e}]")
        return False
    else:
        if killed is True:
            logger.debug(f"Creature kill OK | {name}")
            return True
        else:
            logger.warning(f"Creature kill KO | {name} (NotFound in threads)")
            return False
