#!/usr/bin/env python3
# -*- coding: utf8 -*-

import discord
import time

from loguru import logger

from subcommands import (
    auction,
    bazaar,
    infra,
    godmode,
    singouin,
    user,
    )
from subtasks import channels, healthcheck, ssl_cert, yqueue, pubsub
from variables import env_vars

try:
    intents = discord.Intents.default()
    intents.members = True  # Enable the members intent
    if env_vars['DISCORD_GUILD']:
        bot = discord.Bot(intents=intents, debug_guilds=[env_vars['DISCORD_GUILD']])
    else:
        bot = discord.Bot(intents=intents)
except Exception as e:
    logger.error(f'Discord connection KO [{e}]')
else:
    logger.info('Discord connection OK')


@bot.event
async def on_ready():
    try:
        channel = discord.utils.get(bot.get_all_channels(), name='singouins')
    except Exception as e:
        logger.error(f'Discord on_ready KO [{e}]')
    else:
        if channel:
            logger.info(f'Discord on_ready OK ({bot.user})')
    # Always looping for Pub/Sub task
    bot.loop.create_task(pubsub.check(bot))


# Additionnal error detector to answer properly
@bot.event
async def on_application_command_error(ctx, error):
    """Inform user of errors."""
    if isinstance(error, discord.ext.commands.NoPrivateMessage):
        await ctx.respond(
            "Sorry, this can't be done in DMs.",
            ephemeral=True
            )
    elif isinstance(error, discord.ext.commands.MissingPermissions):
        await ctx.respond(
            "Sorry, you don't have permission to do this.",
            ephemeral=True
            )
    elif isinstance(error, discord.ext.commands.CommandNotFound):
        await ctx.respond(
            "Sorry, unable to find the proper interaction.",
            ephemeral=True
            )
    else:
        raise error


#
# /auction Commands (for @Singouins)
#
try:
    group_auction  = bot.create_group(
        description="Commands related to Auction House usage",
        name='auction',
        )
except Exception as e:
    logger.error(f'[{group_auction}] Command Group KO [{e}]')
else:
    logger.debug(f'[{group_auction}] Command Group OK')
    auction.buy(group_auction)
    auction.remove(group_auction)
    auction.search(group_auction, bot)
    auction.sell(group_auction)
    auction.show(group_auction, bot)
    logger.debug(f'[{group_auction}] Commands OK')
#
# /bazaar Commands (for @Singouins)
#
try:
    group_bazaar  = bot.create_group(
        description="Commands related to Bazaar usage",
        name='bazaar',
        )
except Exception as e:
    logger.error(f'[{group_bazaar}] Command Group KO [{e}]')
else:
    logger.debug(f'[{group_bazaar}] Command Group OK')
    bazaar.ammo(group_bazaar, bot)
    bazaar.item(group_bazaar, bot)
    logger.debug(f'[{group_bazaar}] Commands OK')
#
# /godmode Commands (for @Admins)
#
try:
    group_name     = 'godmode'
    group_godmode = bot.create_group(
        description="Commands related to being THE almighty",
        name=group_name,
        )
except Exception as e:
    logger.error(f'[{group_name}] Command Group KO [{e}]')
else:
    logger.debug(f'[{group_name}] Command Group OK')
    godmode.depop(group_godmode)
    godmode.give(group_godmode)
    godmode.pop(group_godmode)
    godmode.take(group_godmode)
    godmode.reset(group_godmode)
    logger.debug(f'[{group_name}] Commands OK')
#
# /infra Commands (for @Admins)
#
try:
    group_name     = 'infra'
    group_admin = bot.create_group(
        description="Commands related to Infrastructure management",
        name=group_name,
        )
except Exception as e:
    logger.error(f'[{group_name}] Command Group KO [{e}]')
else:
    logger.debug(f'[{group_name}] Command Group OK')
    infra.backup(group_admin)
    infra.deploy(group_admin)
    logger.debug(f'[{group_name}] Commands OK')
#
# /mysingouin Commands (for @Singouins)
#
try:
    group_name     = 'mysingouin'
    group_singouin = bot.create_group(
        description="Commands related to Singouins",
        name=group_name,
        )
except Exception as e:
    logger.error(f'[{group_name}] Command Group KO [{e}]')
else:
    logger.debug(f'[{group_name}] Command Group OK')
    singouin.equipment(group_singouin)
    singouin.highscores(group_singouin, bot)
    singouin.inventory(group_singouin)
    singouin.korp(group_singouin, bot)
    singouin.pa(group_singouin)
    singouin.show(group_singouin, bot)
    singouin.squad(group_singouin, bot)
    singouin.stats(group_singouin, bot)
    singouin.wallet(group_singouin, bot)
    logger.debug(f'[{group_name}] Commands OK')
#
# /user Commands (for @everyone)
#
try:
    group_name = 'user'
    group_user = bot.create_group(
        description="Commands related to Users/Players",
        name=group_name,
        )
except Exception as e:
    logger.error(f'[{group_name}] Command Group KO ({group_name}) [{e}]')
else:
    logger.debug(f'[{group_name}] Command Group OK')
    user.grant(group_user, bot)
    user.link(group_user, bot)
    logger.debug(f'[{group_name}] Commands OK')


# 86400s Tasks (@Daily)
if env_vars['SSL_CHECK']:
    bot.loop.create_task(ssl_cert.validator(bot, 86400))
# 3600s Tasks (@Hourly)
bot.loop.create_task(channels.create(bot, 'Squad', 300))
bot.loop.create_task(channels.cleanup(bot, 'Korp', 300))
# 300s Tasks (@5Minutes)
bot.loop.create_task(channels.create(bot, 'Korp', 300))
bot.loop.create_task(channels.create(bot, 'Squad', 300))
# 60s Tasks (@1Minute)
if env_vars['YQ_CHECK']:
    bot.loop.create_task(yqueue.check(bot, 60))
# Healthcheck server
bot.loop.create_task(healthcheck.start(bot, env_vars['HEALTHCHECK_PORT']))


# Run Discord bot
iter = 0
while iter < 5:
    try:
        bot.run(env_vars['DISCORD_TOKEN'])
        break
    except Exception as e:
        logger.error(f'Discord bot.run KO (Attempt: {iter+1}/5) [{e}]')
        iter += 1
        time.sleep(5)
        continue
