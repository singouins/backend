# -*- coding: utf8 -*-

import math

from loguru import logger
from mongoengine import Q

from mongo.models.Creature import CreatureDocument


def closest_player_from_me(self):
    """
    Fetchs the closest Player from self.

    Parameters: None

    Returns:
        - CreatureDocument
    """

    # Grab the view
    range = 4 + round(self.stats.total.p / 50)

    maxx  = self.creature.x + range
    minx  = self.creature.x - range
    maxy  = self.creature.y + range
    miny  = self.creature.y - range

    try:
        query = (
            Q(x__gte=minx) & Q(x__lte=maxx)
            & Q(y__gte=miny) & Q(y__lte=maxy)
            & Q(race__lt=10)
            )
        Creatures = CreatureDocument.objects.filter(query)
    except CreatureDocument.DoesNotExist:
        logger.debug("CreatureDocument Query KO (404)")
        return None
    except Exception as e:
        logger.error(f'{self.logh} | CreatureDocument Query KO [{e}]')
        return None
    else:
        logger.trace(f'{self.logh} | CreatureDocument Query OK')

    # There is ONLY ONE Player in sight
    if Creatures.count() == 1:
        return Creatures.get()

    """
    # There are Creatures in sight - Lets find if someone has aggro
    Creatures.order_by('korp.rank')
    if Creatures.results[0].aggro > 0:
        # This Creature in sight has the biggest aggro
        # We move towards it
        CreatureTarget = Creatures.results[0]
        logger.trace(
            f'Target found via aggro({CreatureTarget.aggro}): '
            f'[{CreatureTarget.id}] {CreatureTarget.name} '
            f'@({CreatureTarget.x}, {CreatureTarget.y})'
            )
    """

    # There are Creatures in sight - Lets find the closest
    top = 100
    CreatureTarget = None
    for Creature in Creatures:
        if Creature.id == self.creature.id:
            # We are seeing ourself -> NEXT
            continue
        elif Creature.race > 10:
            # We do not move/attack towards another NPC
            pass
            # continue
        else:
            hypot = math.hypot(Creature.x - self.creature.x, Creature.y - self.creature.y)
            if hypot < top:
                CreatureTarget = Creature
                top = hypot
    return CreatureTarget


def next_coords_to_creature(self, CreatureTarget):
    """
    Finds the next hop towards a Creature.

    Parameters:
        - CreatureTarget: RedisCreature Object

    Returns: (x, y)
    """
    # Lets try to move to closest creature
    if self.creature.x == CreatureTarget.x:  # We are already on same X
        x = self.creature.x
    elif self.creature.x > CreatureTarget.x:
        if self.creature.x - 1 == CreatureTarget.x:  # We are already close
            x = self.creature.x
        else:
            x = self.creature.x - 1
    elif self.creature.x < CreatureTarget.x:
        if self.creature.x + 1 == CreatureTarget.x:  # We are already close
            x = self.creature.x
        else:
            x = self.creature.x + 1

    if self.creature.y == CreatureTarget.y:  # We are already on same Y
        y = self.creature.y
    elif self.creature.y > CreatureTarget.y:
        if self.creature.y - 1 == CreatureTarget.y:  # We are already close
            y = self.creature.y
        else:
            y = self.creature.y - 1
    elif self.creature.y < CreatureTarget.y:
        if self.creature.y + 1 == CreatureTarget.y:  # We are already close
            y = self.creature.y
        else:
            y = self.creature.y + 1

    return (x, y)


def is_coords_empty(self, x, y):
    """
    Checks if a set of coordinates is empty or not.

    Parameters:
        - x: INT
        - y: INT

    Returns: bool()
    """
    try:
        occupied = CreatureDocument.objects.filter(x=x, y=y).count() > 0
    except Exception as e:
        logger.error(f'{self.logh} | CreatureDocument Query KO [{e}]')
        return None
    else:
        return not occupied
