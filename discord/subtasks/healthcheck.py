# -*- coding: utf8 -*-

import asyncio
import discord

from loguru import logger

MAX_LATENCY = 30  # seconds


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, bot: discord.Client) -> None:  # noqa: E501
    healthy = bool(
        bot.is_ready()
        and bot.latency is not None
        and bot.latency < MAX_LATENCY
        )
    writer.write(b'OK\n' if healthy else b'FAIL\n')
    await writer.drain()
    writer.close()


#
# Subtask
#
async def start(bot: discord.Client, port: int = 40404) -> None:
    try:
        await asyncio.start_server(
            lambda reader, writer: _handle(reader, writer, bot),
            '127.0.0.1',
            port,
            )
    except Exception as e:
        logger.error(f'Healthcheck server KO [{e}]')
    else:
        logger.debug(f'Healthcheck server OK (127.0.0.1:{port})')
