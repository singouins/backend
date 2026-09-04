# -*- coding: utf8 -*-

import discord

from discord.commands import option
from discord.ext import commands
from loguru import logger

from mongo.models.Creature import CreatureDocument
from mongo.models.Squad import SquadDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.singouin._tools import creature_sprite


def squad(group_singouin, bot):
    @group_singouin.command(
        description='[@Singouins role] Display your Singouin Squad',
        default_permission=False,
        name='squad',
        )
    @commands.has_any_role('Singouins', 'Team')
    @option(
        "singouinuuid",
        description="Singouin ID",
        autocomplete=get_mysingouins_list
        )
    async def squad(
        ctx,
        singouinuuid: str,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_singouin} squad {singouinuuid}')

        file = None

        Creature = CreatureDocument.objects(_id=singouinuuid).get()
        if Creature.squad.id:
            try:
                Squad = SquadDocument.objects(_id=Creature.squad.id).get()
            except SquadDocument.DoesNotExist:
                msg = f'Squad `{Creature.squad.id}` NotFound in DB'
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
            description = f"Your Singouin **{Creature.name}** is not in a Squad"
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

            SquadMembers = CreatureDocument.objects(squad__id=Creature.squad.id)
            SquadMembers = SquadMembers.order_by('squad.rank')

            # Dirty Gruik to find the max(len(Member.name))
            w = max(len(SquadMember.name) for SquadMember in SquadMembers)

            mydesc = ''
            for SquadMember in SquadMembers:
                emojiMyRace = emojiRace[SquadMember.race - 1]
                if SquadMember.id == Squad.leader:
                    # This Singouin is the leader
                    title = ':first_place: Leader'
                else:
                    title = ':second_place: Member'
                level = f"(lvl:{SquadMember.level})"
                mydesc += f"{emojiMyRace} `{SquadMember.name:<{w}} {level:>8}` | {title}\n"

            embed = discord.Embed(
                title="Squad",
                description=mydesc,
                colour=discord.Colour.blue()
                )

            # We check if we have a sprite to add as thumbnail
            if creature_sprite(Creature):
                file = discord.File(f'/tmp/{Creature.id}.png', filename=f'{Creature.id}.png')
                embed.set_thumbnail(url=f'attachment://{Creature.id}.png')
        except Exception as e:
            description = f'Singouin-Squad Query KO [{e}]'
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
            logger.info(f'{h} └──> Singouin-Squad Query OK')
            await ctx.respond(embed=embed, ephemeral=True, file=file)
            return
