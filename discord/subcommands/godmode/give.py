# -*- coding: utf8 -*-

import discord

from discord.commands import option
from discord.ext import commands
from loguru import logger

from mongo.models.Creature import CreatureDocument
from mongo.models.Item import ItemDocument

from subcommands.godmode._autocomplete import (
    get_metanames_list,
    get_rarity_item_list,
    get_singouins_list,
    )

from variables import (
    env_vars,
    metaIndexed,
    rarity_item_types_discord as ritd,
    )


def give(group_godmode):
    @group_godmode.command(
        description='[@Team role] Loot an Item to a Singouin',
        default_permission=False,
        name='give',
        )
    @commands.guild_only()  # Hides the command from the menu in DMs
    @commands.has_any_role('Team')
    @option(
        "singouin_uuid",
        description="Singouin UUID",
        autocomplete=get_singouins_list
        )
    @option(
        "rarity",
        description="Item Rarity",
        autocomplete=get_rarity_item_list
        )
    @option(
        "metatype",
        description="Item Type",
        autocomplete=discord.utils.basic_autocomplete(
            [
                discord.OptionChoice("Armor", value='armor'),
                discord.OptionChoice("Weapon", value='weapon'),
                ]
            )
        )
    @option(
        "metaid",
        description="Item Name",
        autocomplete=get_metanames_list,
        )
    @option(
        "bound_type",
        description="Bound Type",
        choices=['BoE', 'BoP'],
        )
    async def give(
        ctx,
        singouin_uuid: str,
        rarity: str,
        metatype: str,
        metaid: int,
        bound_type: str,
    ):

        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_godmode} give {singouin_uuid} {rarity} {metatype} {metaid} {bound_type}')  # noqa: E501

        try:
            Creature = CreatureDocument.objects(_id=singouin_uuid).get()
        except CreatureDocument.DoesNotExist:
            msg = 'Singouin NotFound'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Godmode-Give Query KO ({msg})')
            return

        try:
            meta = metaIndexed[metatype][metaid]
            if metatype == 'armor':
                max_ammo = None
            elif metatype == 'weapon':
                max_ammo = meta['max_ammo']
            else:
                max_ammo = None

            if bound_type == 'BoE':
                bound = False
            else:
                bound = True

            Item = ItemDocument(
                ammo=max_ammo,
                bearer=singouin_uuid,
                bound=bound,
                bound_type=bound_type,
                metaid=metaid,
                metatype=metatype,
                rarity=rarity,
                )
            Item.save()
        except Exception as e:
            description = f'Godmode-Give Query KO [{e}]'
            logger.error(f'{h} └──> {description}')
            await ctx.respond(
                embed=discord.Embed(
                    description=description,
                    colour=discord.Colour.red(),
                    )
                )
            return

        embed = discord.Embed(
            title="A new item appears!",
            colour=discord.Colour.green()
            )

        embed_field_name = f"{ritd[Item.rarity]} {meta['name']}"
        embed_field_value  = f"> Bearer : `{Creature.name}`\n"
        embed_field_value += f"> Bearer : `UUID({Item.bearer})`\n"
        embed_field_value += f"> Bound : `{Item.bound} ({Item.bound_type})`\n"

        if max_ammo:
            embed_field_value += f"> Ammo : `{Item.ammo}/{max_ammo}`\n"

        embed.add_field(
            name=f'**{embed_field_name}**',
            value=embed_field_value,
            inline=True,
            )

        embed.set_footer(text=f"ItemUUID: {Item.id}")

        URI_PNG = f'sprites/{Item.metatype}s/{Item.metaid}.png'
        logger.debug(f"[embed.thumbnail] {env_vars['URL_ASSETS']}/{URI_PNG}")
        embed.set_thumbnail(url=f"{env_vars['URL_ASSETS']}/{URI_PNG}")

        await ctx.respond(embed=embed)
        logger.info(f'{h} └──> Godmode-Give Query OK')
