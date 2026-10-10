# -*- coding: utf8 -*-

import datetime
import json

from loguru import logger
from mongoengine import Q

from mongo.models.Creature import CreatureDocument
from mongo.models.Instance import InstanceDocument

from utils.redis import r, purge_creature_keys, purge_instance_keys
from variables import PS_AI_CREATURE


def leave_instance(creature: CreatureDocument, instance: InstanceDocument) -> str:
    """
    Takes a Creature out of an Instance, whatever the reason.

    Used by the leave route today; death ejection will call it with the same
    arguments. The caller is responsible for the HTTP answer and the Discord
    queue message. Exceptions propagate to the caller.

    In order:
    - if other players remain, record the Creature in Instance.leavers
      (no re-entry) BEFORE detaching: if this fails, the Creature stays inside
      and the caller's "leave KO" answer is true;
    - detach the Creature (instance/x/y None);
    - purge every Redis key of the Creature (PA pools, actives, ammo);
    - if the Creature was the last player: kill every monster (ai-creature
      pubsub, then delete) and delete the Instance.

    :param creature: The leaving Creature.
    :param instance: The Instance being left.

    :return: 'closed' when the Instance was deleted, 'left' otherwise.
    """
    h = f'[Creature.id:{creature.id}]'

    query_players = (
        Q(instance=instance.id) &
        Q(account__ne=None)
        )
    Players = CreatureDocument.objects.filter(query_players)
    last_player = Players.count() == 1

    if last_player:
        logger.trace(f'{h} Instance({instance.id}) Last Player inside')
    else:
        logger.debug(f'{h} Not the last in Instance (pcs:{Players.count()})')
        # The Creature may not re-enter this instance later on.
        # Recorded BEFORE detaching, see the docstring
        InstanceDocument.objects(_id=instance.id).update_one(
            add_to_set__leavers=creature.id,
            )

    creature.instance = None
    creature.x = None
    creature.y = None
    creature.updated = datetime.datetime.utcnow()
    creature.save()

    # Outside an instance nothing of the creature exists in Redis
    purge_creature_keys(creatureuuid=creature.id, instanceuuid=instance.id)

    if not last_player:
        return 'left'

    # We need to kill all NPC inside the instance
    query_monsters = (
        Q(instance=instance.id) &
        Q(account=None)
        )
    Monsters = CreatureDocument.objects.filter(query_monsters)

    for Monster in Monsters:
        logger.trace(f'{h} Instance({instance.id}) Cleaning')
        # We send in pubsub channel for IA to spawn the Mobs
        try:
            r.publish(
                PS_AI_CREATURE,
                json.dumps({
                    "action": 'kill',
                    "instance": instance.to_json(),
                    "creature": Monster.to_json(),
                    }),
                )
        except Exception as e:
            msg = f'{h} Publish({PS_AI_CREATURE}/kill) KO [{e}]'
            logger.error(msg)

        # Nothing of a dead mob may outlive it: its PA pools and actives go
        purge_creature_keys(creatureuuid=Monster.id, instanceuuid=instance.id)
        # We kill it
        # ALWAYS KILL CREATURE THE LAST
        Monster.delete()

    instance.delete()
    # A deleted Instance takes everything scoped by it with it, whoever the bearer
    purge_instance_keys(instanceuuid=instance.id)
    return 'closed'
