# -*- coding: utf8 -*-

import asyncio
import discord
import json
import yarqueue

from loguru import logger

from mongo.models.User import UserDocument
from utils.redis import r
from variables import (
    env_vars,
    metaIndexed,
    rarity_item_types_discord,
    rarity_item_types_integer,
    )


#
# Helpers
#
async def send_message(bot: discord.Client, answer: str, embed: discord.Embed, scope: dict):
    for channel_name in [scope.lower(), f"{scope.lower().split('-')[0]}s-wildcard"]:
        try:
            channel = discord.utils.get(bot.get_all_channels(), name=channel_name)
            if channel:
                logger.trace(f'Send message >> (channel:{channel.name})')
                await channel.send(answer, embed=embed)
                logger.debug(f'Send message OK (channel:{channel_name})')
            else:
                logger.warning(f"Channel Query KO (channel:{channel_name}) - NotFound")
        except Exception as e:
            logger.error(f'Send message KO (channel:{channel_name}) [{e}]')


#
# Subtask
#
async def check(bot: discord.Client, timer: int):
    while bot.is_ready():
        if bot.user:
            # Opening Queue
            msgs = yarqueue.Queue(name=env_vars['YQ_DISCORD'], redis=r)

            if msgs is None:
                # If no msgs are received, GOTO next loop
                logger.debug('Message Queue KO - GOTO next loop')
                continue

            if len(msgs) == 0:
                logger.debug('Message Queue OK - But empty')
            else:
                logger.debug(f'Message Queue OK - Got {len(msgs)} msgs')
                # msgs_list = list(msgs).reverse()

            for msg_str in msgs:
                msg = json.loads(msg_str)
                logger.trace(f'Message type {type(msg)} Received {msg}')
                if msg['payload'] is None:
                    # We are reading a WEIRD message: We don't do anything
                    logger.trace(f'Message skipped ({msg}) - No Payload')
                    continue

                if msg['scope'] is None:
                    # We DO NOT HAVE have a Scope: We don't do anything
                    logger.trace(f'Message skipped ({msg}) - No Scope')
                    continue

                if msg['embed'] is None:
                    # We are reading a STANDARD message: We prepare to send
                    logger.trace('Message STANDARD')
                    answer = msg['payload']
                    embed  = msg['embed']
                elif msg['payload']['winner'] and msg['payload']['item']:
                    # We are reading a LOOT message: We prepare to send
                    logger.trace('Message LOOT')
                    item = msg['payload']['item']
                    winner = msg['payload']['winner']
                    User = UserDocument.objects(_id=winner['id'])

                    if User.discord.name:
                        # The Singouin who looted is linked on Discord
                        logger.trace(f"Discord Name (d_name:{User.d_name})")
                        (name, discriminator) = User.d_name.split('#')
                        # The loot winner has a registered Discord Acc
                        discorduser = discord.utils.get(
                            bot.get_all_members(),
                            name=name,
                            discriminator=discriminator
                            )
                        # We add that info into the proper var
                        if discorduser:
                            logger.debug(f'Discord User Query OK (discorduser:{discorduser})')
                            header = f"{discorduser.mention} (**{winner['name']}**) looted that !"
                        else:
                            header = f"Somebody ({winner['name']}) looted that !"
                            logger.warning('Discord User Query KO - NotFound')
                    else:
                        # The Singouin who looted is NOT linked on Discord
                        header = f"Somebody ({winner['name']}) looted that !"
                        logger.debug('User Not Linked - Cannot @tag him')

                    answer = None
                    embed = discord.Embed(
                        color=rarity_item_types_integer[item['rarity']]
                        )

                    embed_field_name = (
                        f"{rarity_item_types_discord[item['rarity']]} "
                        f"{metaIndexed[item['metatype']][item['metaid']]}"
                        )

                    embed_field_value  = f"> Bound : `{item['bound']} ({item['bound_type']})`\n"
                    embed_field_value += f"> State : `{item['state']}`\n"
                    embed_field_value += f"> Bearer : `UUID({item['bearer']})`\n"

                    if item['ammo'] is not None:
                        embed_field_value += f"> Ammo : `{item['ammo']}`\n"

                    embed_field_value += header

                    embed.add_field(
                        name=embed_field_name,
                        value=embed_field_value,
                        inline=True,
                        )

                    URI_PNG = f"sprites/{item['metatype']}s/{item['metaid']}.png"
                    URL_PNG = f"{env_vars['URL_ASSETS']}/{URI_PNG}"
                    logger.debug(f"[embed.thumbnail] {URL_PNG}")
                    embed.set_thumbnail(url=URL_PNG)

                    embed.set_footer(text=f"ItemUUID: {item['id']}")
                else:
                    # We are reading a Unknown message: We don't do anything
                    logger.trace(f'Message skipped ({msg}) - Unknown')
                    continue

                await send_message(bot, answer, embed, msg['scope'])
        await asyncio.sleep(timer)
