# -*- coding: utf8 -*-

import time
import threading

from abc import ABC, abstractmethod
from loguru  import logger
from random import randint

from mongo.models.Creature import CreatureDocument
from mongo.models.Instance import InstanceDocument
from utils.requests import resolver_move
from utils.redis import r
from utils.computation import (
    closest_player_from_me,
    next_coords_to_creature,
    is_coords_empty,
    )
from variables import env_vars


class Mob(ABC, threading.Thread):

    @abstractmethod
    def __init__(self, creatureuuid: str):
        threading.Thread.__init__(self)

        # We replicate Creature attibutes into Mob object
        try:
            self.creature = CreatureDocument.objects(_id=creatureuuid).get()
        except CreatureDocument.DoesNotExist:
            logger.debug("CreatureDocument Query KO (404)")
        else:
            logger.trace(f'CreatureDocument: {self.creature.to_json()}')

        # We add Instance info as we need it
        try:
            self.instance = InstanceDocument.objects(_id=self.creature.instance).get()
        except InstanceDocument.DoesNotExist:
            logger.debug("InstanceDocument Query KO (404)")
        else:
            logger.trace(f'InstanceDocument: {self.instance.to_json()}')

        # Logging headers
        self.logh = f'[{self.creature.id}] {self.creature.name}'

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def attack(self):
        pass

    @abstractmethod
    def hit(self):
        pass

    def move(self):
        if self.pa.blue > 4 and randint(0, 1):
            logger.success(f'{self.logh} | Will move')
            self.set_pos()
        else:
            logger.warning(f'{self.logh} | Will not move')

    def sleep(self):
        logger.debug(f'{self.logh} | Will rest ({self.instance.tick}s)')
        time.sleep(self.instance.tick)

    def status(self):
        pas = f'[🔴 :{self.pa.red},🔵 :{self.pa.blue}] '
        pos = f'@(x:{self.creature.x},y:{self.creature.y})'
        hp = f'{self.creature.hp.current}/{self.creature.hp.max}HP'
        logger.debug(f'{self.logh} | Alive:{hp} {pas} {pos}')

#
#
#
    def get_pa(self):
        # Constants
        RED_PA_MAX = 16
        BLUE_PA_MAX = 8
        PA_DURATION = self.instance.tick

        # Define a simple class to store PA values
        class PA:
            def __init__(self):
                self.red = 0
                self.blue = 0

        pa_info = {
            'blue': {
                'key': f"{env_vars['API_ENV']}:pas:{self.creature.id}:blue",
                'max_pa': BLUE_PA_MAX,
                'max_ttl': BLUE_PA_MAX * PA_DURATION,
                'current_pa': BLUE_PA_MAX,
            },
            'red': {
                'key': f"{env_vars['API_ENV']}:pas:{self.creature.id}:red",
                'max_pa': RED_PA_MAX,
                'max_ttl': RED_PA_MAX * PA_DURATION,
                'current_pa': RED_PA_MAX,
            }
        }

        # Initialize self.pa as an instance of the PA class if it doesn't exist
        if not hasattr(self, 'pa'):
            self.pa = PA()

        for pa_color, pa_data in pa_info.items():
            if r.exists(pa_data['key']):
                pa_info[pa_color]['current_pa'] = int(
                    round(pa_data['max_ttl'] - abs(r.ttl(pa_data['key'])) / PA_DURATION)
                    )

            # Dynamically assign the current_pa to self.pa based on the pa_type
            setattr(self.pa, pa_color, pa_data['current_pa'])

    def get_creature(self):
        try:
            Creature = CreatureDocument.objects(_id=self.creature.id).get()
        except CreatureDocument.DoesNotExist:
            logger.debug("CreatureDocument Query KO (404)")
        except Exception as e:
            logger.error(f'{self.logh} | CreatureDocument Query KO [{e}]')
        else:
            self.creature = Creature
            logger.trace(f'{self.logh} | CreatureDocument Query OK')

#
#
#
    def set_pos(self):
        # We check the closest PC in sight
        CreatureTarget = closest_player_from_me(self)
        if CreatureTarget:
            # We have a close PC in sight
            (nextx, nexty) = next_coords_to_creature(self, CreatureTarget)
        else:
            logger.debug(f'{self.logh} | No close Creature. Stop here')
            return None

        # logger.info(f'closest:{CreatureTarget}')
        # logger.info(f'x:{nextx}, y:{nexty}')

        # Collision check
        if not is_coords_empty(self, x=nextx, y=nexty):
            # There is a Creature on these coordinates
            logger.debug(f"{self.logh} | Move KO | (Tile busy @({nextx}, {nexty}))")
            return
        else:
            # There is no one on these coordinates
            logger.debug(f"{self.logh} | Move >> | (Tile empty @({nextx, nexty}))")

        # Proximity check
        if (nextx, nexty) and \
           (self.creature.x, self.creature.y) == (nextx, nexty):
            logger.debug(
                f"{self.logh} | Move KO | "
                f"(Already close to "
                f"[{CreatureTarget.id}] {CreatureTarget.name} "
                f"@({CreatureTarget.x},{CreatureTarget.y}))"
                )
            return
        else:
            logger.debug(
                f"{self.logh} | Move >> | "
                f"(Not close enough to "
                f"[{CreatureTarget.id}] {CreatureTarget.name} "
                f"@({CreatureTarget.x},{CreatureTarget.y}))"
                )

        # We can move, path clear
        logger.debug(
            f"{self.logh} | Move >> | "
            f"from (x:{self.creature.x},y:{self.creature.y}) "
            f"to (x:{nextx},y:{nexty}))"
            )
        try:
            payload = resolver_move(self, nextx, nexty)
        except Exception as e:
            logger.error(f'{self.logh} | Request KO [{e}]')
            return

        if payload is None or 'result' not in payload:
            # Here we have a weird answer from Resolver
            logger.warning(f"{self.logh} | Move KO | Resolver response is KO")
            return

        if payload['result']['success']:
            logger.debug(
                f"{self.logh} | Move OK | "
                f"from (x:{self.creature.x},y:{self.creature.y}) "
                f"to (x:{nextx},y:{nexty}))"
                )
        else:
            logger.warning(
                f"{self.logh} | Move KO | "
                f"from (x:{self.creature.x},y:{self.creature.y}) "
                f"to (x:{nextx},y:{nexty}))"
                )
