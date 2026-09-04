# -*- coding: utf8 -*-

import discord
import json
import redis.asyncio as redis

from loguru import logger

from mongo.models.User import UserDocument

from variables import env_vars

r = redis.Redis(
    host=env_vars['REDIS_HOST'],
    port=env_vars['REDIS_PORT'],
    db=env_vars['REDIS_BASE']
    )
pubsub = r.pubsub()


#
# Subtask
#
async def check(bot: discord.Client) -> None:
    if not env_vars.get('PS_DISCORD'):
        return

    while bot.is_ready():
        if bot.user:
            await pubsub.subscribe(env_vars['PS_DISCORD'])

            # Continuously listen for messages
            async for message in pubsub.listen():
                logger.trace(f'Pub/Sub received: {message}')
                if message['type'] == 'message':
                    data = message['data'].decode('utf-8')

                    # Parse the data to find the recipient
                    account_uuid = json.loads(data).get('creature', {}).get('account')
                    if not account_uuid:
                        logger.warning("No account UUID found in message.")
                        continue

                    # Get the User
                    try:
                        User = UserDocument.objects(_id=account_uuid).get()
                    except UserDocument.DoesNotExist:
                        logger.warning("UserDocument Query KO (404)")
                        continue
                    except Exception as e:
                        logger.error(f'MongoDB Query KO [{e}]')
                    else:
                        if not User:
                            logger.warning("UserDocument not found.")
                            continue
                        if not User.discord.name:
                            logger.warning("User not linked.")
                            continue

                    # Loop through all guilds the bot is in
                    # It should be only one, but ...
                    for guild in bot.guilds:
                        # Search for the user in the guild
                        member = discord.utils.get(guild.members, name=User.discord.name)

                        if not member:
                            logger.warning("Member not found in this guild.")
                            continue

                        # Send the DM
                        try:
                            await member.send(json.loads(data).get("msg"))
                            logger.trace(f"Message sent to {member.name}")
                        except discord.Forbidden:
                            logger.warning("I cannot send a DM to this member.")
                        except Exception as e:
                            logger.error(f"I failed to send a DM to this member. [{e}]")
