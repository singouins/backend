# -*- coding: utf8 -*-

import discord

from discord.commands import option
from discord.ext import commands
from loguru import logger

from mongo.models.Creature import CreatureDocument
from mongo.models.Korp import KorpDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.singouin._tools import creature_sprite


def korp(group_singouin, bot):
    @group_singouin.command(
        description='[@Singouins role] Display your Singouin Korp',
        default_permission=False,
        name='korp',
        )
    @commands.has_any_role('Singouins', 'Team')
    @option(
        "singouinuuid",
        description="Singouin ID",
        autocomplete=get_mysingouins_list
        )
    async def korp(
        ctx,
        singouinuuid: str,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_singouin} korp {singouinuuid}')

        file = None

        Creature = CreatureDocument.objects(_id=singouinuuid).get()
        if Creature.korp.id:
            try:
                Korp = KorpDocument.objects(_id=Creature.korp.id).get()
            except KorpDocument.DoesNotExist:
                msg = f'Korp `{Creature.korp.id}` NotFound in DB'
                logger.warning(msg)
                await ctx.respond(
                    embed=discord.Embed(
                        description=msg,
                        colour=discord.Colour.orange(),
                        ),
                    ephemeral=True,
                    )
                return
        else:
            description = f"Your Singouin **{Creature.name}** is not in a Korp"
            logger.debug(f'{h} └──> {description}')
            await ctx.respond(
                embed=discord.Embed(
                    description=description,
                    colour=discord.Colour.red(),
                    ),
                ephemeral=True,
                )
            return

        try:
            emojiRace = [
                discord.utils.get(bot.emojis, name='raceC'),
                discord.utils.get(bot.emojis, name='raceG'),
                discord.utils.get(bot.emojis, name='raceM'),
                discord.utils.get(bot.emojis, name='raceO'),
                ]

            KorpMembers = CreatureDocument.objects(korp__id=Creature.korp.id)
            KorpMembers = KorpMembers.order_by('korp.rank')

            # Dirty Gruik to find the max(len(Member.name))
            w = max(len(KorpMember.name) for KorpMember in KorpMembers)

            mydesc = ''
            for KorpMember in KorpMembers:
                emojiMyRace = emojiRace[KorpMember.race - 1]
                if KorpMember.id == Korp.leader:
                    # This Singouin is the leader
                    title = ':first_place: Leader'
                else:
                    title = ':second_place: Member'
                level = f"(lvl:{KorpMember.level})"
                mydesc += f"{emojiMyRace} `{KorpMember.name:<{w}} {level:>8}` | {title}\n"

            embed = discord.Embed(
                title=f"Korp <{Korp.name}>",
                description=mydesc,
                colour=discord.Colour.blue()
                )

            # We check if we have a sprite to add as thumbnail
            if creature_sprite(Creature):
                file = discord.File(f'/tmp/{Creature.id}.png', filename=f'{Creature.id}.png')
                embed.set_thumbnail(url=f'attachment://{Creature.id}.png')
        except Exception as e:
            description = f'Singouin-Korp Query KO [{e}]'
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
            logger.info(f'{h} └──> Singouin-Korp Query OK')
            await ctx.respond(embed=embed, ephemeral=True, file=file)
            return
