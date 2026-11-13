# -*- coding: utf8 -*-

import asyncio

from abc import ABC, abstractmethod
from loguru  import logger
from random import randint

from mongo.models.Creature import CreatureDocument
from mongo.models.Instance import InstanceDocument
from mongo.utils import JSON_OPTIONS
from utils.requests import resolver_move
from utils.redis import r
from utils.computation import (
    closest_player_from_me,
    next_coords_to_creature,
    is_coords_empty,
    )
from variables import env_vars


class Mob(ABC):

    @abstractmethod
    def __init__(self, creatureuuid: str):
        # Synchronous on purpose: constructed via asyncio.to_thread() from
        # creature_pop() rather than being made async itself, so the sync
        # mongoengine calls here don't need an async-aware constructor.

        # We replicate Creature attibutes into Mob object
        try:
            self.creature = CreatureDocument.objects(_id=creatureuuid).get()
        except CreatureDocument.DoesNotExist:
            logger.debug("CreatureDocument Query KO (404)")
        else:
            logger.trace(f'CreatureDocument: {self.creature.to_json(json_options=JSON_OPTIONS)}')

        # We add Instance info as we need it
        try:
            self.instance = InstanceDocument.objects(_id=self.creature.instance).get()
        except InstanceDocument.DoesNotExist:
            logger.debug("InstanceDocument Query KO (404)")
        else:
            logger.trace(f'InstanceDocument: {self.instance.to_json(json_options=JSON_OPTIONS)}')

        # Logging headers
        self.logh = f'[{self.creature.id}] {self.creature.name}'

    @abstractmethod
    async def run(self):
        pass

    @abstractmethod
    def attack(self):
        pass

    @abstractmethod
    def hit(self):
        pass

    async def move(self):
        if self.pa.blue > 4 and randint(0, 1):
            logger.success(f'{self.logh} | Will move')
            await self.set_pos()
        else:
            logger.warning(f'{self.logh} | Will not move')

    async def sleep(self):
        logger.debug(f'{self.logh} | Will rest ({self.instance.tick}s)')
        await asyncio.sleep(self.instance.tick)

    def status(self):
        pas = f'[🔴 :{self.pa.red},🔵 :{self.pa.blue}] '
        pos = f'@(x:{self.creature.x},y:{self.creature.y})'
        hp = f'{self.creature.hp.current}/{self.creature.hp.max}HP'
        logger.debug(f'{self.logh} | Alive:{hp} {pas} {pos}')

#
#
#
    async def get_pa(self):
        # Constants
        # Red regenerates 1 PA per Instance tick, blue 1 PA per 2 ticks
        # (same rule as api/utils/pa.py and the resolver)
        RED_PA_MAX = 16
        BLUE_PA_MAX = 8
        RED_PA_DURATION = self.instance.tick
        BLUE_PA_DURATION = 2 * self.instance.tick

        # Define a simple class to store PA values
        class PA:
            def __init__(self):
                self.red = 0
                self.blue = 0

        # Initialize self.pa as an instance of the PA class if it doesn't exist
        if not hasattr(self, 'pa'):
            self.pa = PA()

        # Full pools unless Redis says otherwise
        current = {'red': RED_PA_MAX, 'blue': BLUE_PA_MAX}
        try:
            # One FCALL_RO pa_read (library functions_pa), as the API, discord
            # and the resolver read: a PA only counts once fully regenerated.
            # KEYS: blue first; ARGV: red first
            red_pa, _, _, blue_pa, _, _ = await r.fcall_ro(
                'pa_read', 2,
                f"{env_vars['API_ENV']}:pas:{self.creature.id}:blue",
                f"{env_vars['API_ENV']}:pas:{self.creature.id}:red",
                RED_PA_DURATION, BLUE_PA_DURATION, RED_PA_MAX, BLUE_PA_MAX,
                )
            current = {'red': red_pa, 'blue': blue_pa}
        except Exception as e:
            # Redis hiccup (pool exhaustion, transient disconnect, ...):
            # fall back to full pools rather than letting this crash the
            # whole Creature task.
            logger.error(f'{self.logh} | Redis PA Query KO [{e}]')

        self.pa.red = current['red']
        self.pa.blue = current['blue']

    async def get_creature(self):
        try:
            Creature = await asyncio.to_thread(
                lambda: CreatureDocument.objects(_id=self.creature.id).get()
                )
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
    async def set_pos(self):
        # We check the closest PC in sight
        CreatureTarget = await asyncio.to_thread(closest_player_from_me, self)
        if CreatureTarget:
            # We have a close PC in sight
            (nextx, nexty) = next_coords_to_creature(self, CreatureTarget)
        else:
            logger.debug(f'{self.logh} | No close Creature. Stop here')
            return None

        # logger.info(f'closest:{CreatureTarget}')
        # logger.info(f'x:{nextx}, y:{nexty}')

        # Collision check
        if not await asyncio.to_thread(is_coords_empty, self, x=nextx, y=nexty):
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
            payload = await resolver_move(self, nextx, nexty)
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
