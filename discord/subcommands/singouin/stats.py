# -*- coding: utf8 -*-

import discord

from datetime import datetime, timedelta
from discord.commands import option
from discord.ext import commands
from loguru import logger

from mongo.models.Creature import CreatureDocument
from mongo.models.Aggro import AggroDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.singouin._tools import creature_sprite


def stats(group_singouin, bot):
    @group_singouin.command(
        description='[@Singouins role] Display your Singouin Stats',
        default_permission=False,
        name='stats',
        )
    @commands.has_any_role('Singouins')
    @option(
        "singouinuuid",
        description="Singouin UUID",
        autocomplete=get_mysingouins_list
        )
    async def stats(
        ctx,
        singouinuuid: str,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_singouin} stats {singouinuuid}')

        file = None

        try:
            Creature = CreatureDocument.objects(_id=singouinuuid).get()
        except CreatureDocument.DoesNotExist:
            msg = 'Singouin NotFound'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Singouin-Stats Query KO ({msg})')
            return

        # Getting Aggro
        # Perform the aggregation
        pipeline = [
            {
                "$match": {
                    "created": {
                        "$gte": datetime.utcnow() - timedelta(hours=48),
                        "$lte": datetime.utcnow()
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_amount": {"$sum": "$amount"}
                }
            }
        ]
        # Reading the aggregated result
        Aggro = list(AggroDocument.objects.aggregate(*pipeline))
        if Aggro:
            aggro = Aggro[0].get('total_amount', 0)
        else:
            aggro = 0

        try:
            embed = discord.Embed(
                title=Creature.name,
                description=(
                    f":heart_decoration: : `{Creature.hp.max}/{Creature.hp.max} HP`\n"
                    f":anger: : `{aggro}`\n"
                    ),
                colour=discord.Colour.blue()
            )

            emojiStats = {
                'b': discord.utils.get(bot.emojis, name='statB'),
                'g': discord.utils.get(bot.emojis, name='statG'),
                'm': discord.utils.get(bot.emojis, name='statM'),
                'p': discord.utils.get(bot.emojis, name='statP'),
                'r': discord.utils.get(bot.emojis, name='statR'),
                'v': discord.utils.get(bot.emojis, name='statV'),
                }

            # We generate base Stats field
            value = ''
            for stat in emojiStats:
                value += f"> {emojiStats[stat]} : `{getattr(Creature.stats.total, stat)}`\n"
            embed.add_field(name='**Base Stats**', value=value, inline=True)

            """
            # We generate DEF Stats field
            value  = f"> :dash: : `{Stats.dodge}`\n"
            value += f"> :shield: : `{Stats.parry}`\n"
            value += "▬\n"
            value += f"> :shield: : `{Stats.arm_b}` (B/:gun:)\n"
            value += f"> :shield: : `{Stats.arm_p}` (P/:axe:)\n"
            embed.add_field(name='**DEF Stats**', value=value, inline=True)

            # We generate OFF Stats field
            value  = f"> :axe: : `{Stats.capcom}`\n"
            value += f"> :gun: : `{Stats.capsho}`\n"
            embed.add_field(name='**OFF Stats**', value=value, inline=True)
            """

            # We check if we have a sprite to add as thumbnail
            if creature_sprite(Creature):
                file = discord.File(f'/tmp/{Creature.id}.png', filename=f'{Creature.id}.png')
                embed.set_thumbnail(url=f'attachment://{Creature.id}.png')
        except Exception as e:
            description = f'Singouin-Stats Query KO [{e}]'
            logger.error(f'{h} └──> {description}')
            await ctx.respond(
                embed=discord.Embed(
                    description=description,
                    colour=discord.Colour.red(),
                    ),
                ephemeral=True,
                )
            return
        else:
            logger.info(f'{h} └──> Singouin-Stats Query OK')
            await ctx.respond(embed=embed, ephemeral=True, file=file)
            return
