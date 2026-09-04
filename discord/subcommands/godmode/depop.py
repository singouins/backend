# -*- coding: utf8 -*-

import discord

from discord.commands import option
from discord.ext import commands
from loguru import logger

from mongo.models.Creature import CreatureDocument

from subcommands.godmode._autocomplete import (
    get_instances_list,
    get_monsters_in_instance_list
    )

from utils.redis import cput
from variables import (
    env_vars,
    rarity_monster_types_discord as rmtd,
    )


def depop(group_godmode):
    @group_godmode.command(
        description='[@Team role] Kill a Monster',
        default_permission=False,
        name='depop',
        )
    @commands.guild_only()  # Hides the command from the menu in DMs
    @commands.has_any_role('Team')
    @option(
        "instance_uuid",
        description="Instance UUID",
        autocomplete=get_instances_list
        )
    @option(
        "creature_uuid",
        description="Creature UUID",
        autocomplete=get_monsters_in_instance_list
        )
    async def depop(
        ctx,
        instance_uuid: str,
        creature_uuid: str,
    ):

        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_godmode} depop {instance_uuid} {creature_uuid}')

        try:
            Creature = CreatureDocument.objects(_id=creature_uuid).get()
        except CreatureDocument.DoesNotExist:
            msg = 'Singouin NotFound'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Godmode-Depop Query KO ({msg})')
            return

        logger.trace(f"{h} ├──> Godmode-Depop {rmtd[Creature.rarity]} {Creature.name}")

        # WE WILL KILL HERE ONLY NON PLAYABLE CREATURES FOR SAFETY
        if Creature.account:
            msg = 'You can only kill NPC Creatures'
            logger.warning(msg)
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            return

        try:
            # It is a NON playable Creature (Monster)
            # We destroy the Creature
            Creature.delete()
            # We put the info in pubsub channel for IA to regulate the instance
            cput(f"ai-creature-{env_vars['API_ENV'].lower()}", {
                "action": 'kill',
                "creature": Creature.to_json(),
                })
        except Exception as e:
            description = f'Godmode-Depop Query KO [{e}]'
            logger.error(f'{h} └──> {description}')
            await ctx.respond(
                embed=discord.Embed(
                    description=description,
                    colour=discord.Colour.red(),
                    )
                )
            return
        else:
            embed = discord.Embed(
                title="A creature slowly dies!",
                colour=discord.Colour.green()
                )

            embed_field_value  = f"> Instance : `{Creature.instance}`\n"
            embed_field_value += f"> Level : `{Creature.level}`\n"
            embed_field_value += f"> Position : `({Creature.x},{Creature.y})`\n"

            embed.add_field(
                name=f'{rmtd[Creature.rarity]} **{Creature.name}**',
                value=embed_field_value,
                inline=True,
                )

            embed.set_footer(text=f"CreatureUUID: {Creature.id}")

            URI_PNG = f'sprites/creatures/{Creature.race}.png'
            logger.debug(f"[embed.thumbnail] {env_vars['URL_ASSETS']}/{URI_PNG}")
            embed.set_thumbnail(url=f"{env_vars['URL_ASSETS']}/{URI_PNG}")

            await ctx.respond(embed=embed)
            logger.info(f'{h} └──> Godmode-Depop Query OK')
