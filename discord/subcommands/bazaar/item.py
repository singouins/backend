# -*- coding: utf8 -*-

import datetime
import discord

from discord.commands import option
from loguru import logger

from mongo.models.Highscore import HighscoreDocument
from mongo.models.Item import ItemDocument
from mongo.models.Satchel import SatchelDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.bazaar._autocomplete import get_singouin_saleable_item_list

from variables import (
    item_types_discord as itd,
    metaIndexed,
    rarity_item_types_discord as ritd,
    RARITY_ITEM,
    )


def item(group_bazaar, bot):
    @group_bazaar.command(
        description='[@Singouins role] Buy/Sell items to the Bazaar',
        default_permission=False,
        name='item',
        )
    @option(
        "singouin_uuid",
        description="Singouin UUID",
        autocomplete=get_mysingouins_list
        )
    @option(
        "action_type",
        description="Bargain Type",
        choices=['Sell']
        )
    @option(
        "item_uuid",
        description="Item UUID",
        autocomplete=get_singouin_saleable_item_list
        )
    async def ammo(
        ctx: discord.ApplicationContext,
        singouin_uuid: str,
        action_type: str,
        item_uuid: str,
    ):

        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_bazaar} ammo {singouin_uuid} {action_type} {item_uuid}')

        try:
            Satchel = SatchelDocument.objects(_id=singouin_uuid).get()
        except SatchelDocument.DoesNotExist:
            msg = 'Satchel NotFound'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Bazaar-Sell Query KO ({msg})')
            return

        try:
            Highscore = HighscoreDocument.objects(_id=singouin_uuid).get()
        except HighscoreDocument.DoesNotExist:
            msg = 'HighscoreDocument NotFound (404)'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Bazaar-Sell Query KO ({msg})')
            return

        try:
            Item = ItemDocument.objects(_id=item_uuid, auctioned=False, bearer=singouin_uuid).get()
        except ItemDocument.DoesNotExist:
            msg = 'Item NotFound or not matching criterias'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Bazaar-Sell Query KO ({msg})')
            return
        else:
            meta = metaIndexed[Item.metatype][Item.metaid]
            sizex, sizey = map(int, meta['size'].split("x"))
            item_price = sizex * sizey * (meta['tier'] + 1) * RARITY_ITEM.index(Item.rarity) // 2

        try:
            # We do the financial transaction
            Satchel.currency.banana += item_price
            Satchel.updated = datetime.datetime.utcnow()
            Satchel.save()
            # We shelve the Item
            Item.bearer = "00000000-cafe-cafe-cafe-000000000000"
            Item.bound = False
            Item.state = 100
            Item.updated = datetime.datetime.utcnow()
            Item.save()
            # Highscore
            Highscore.internal.item.sold += 1
            Highscore.save()
        except Exception as e:
            description = f'Bazaar-Sell Query KO [{e}]'
            logger.error(f'{h} └──> {description}')
            await ctx.respond(
                embed=discord.Embed(
                    description=description,
                    colour=discord.Colour.red(),
                    ),
                ephemeral=True,
                )
            return

        embed = discord.Embed(
            title="Sold to the Bazaar:",
            description=f"> {itd[Item.metatype]} {ritd[Item.rarity]} **{meta['name']}** (Price:{item_price})",  # noqa: E501
            colour=discord.Colour.green(),
            )
        embed.set_footer(text=f"Account balance: {Satchel.currency.banana} 🍌")

        # We add Thumbnail
        file = discord.File('/code/resources/bazaar_256x256.png', filename='bazaar.png')
        embed.set_thumbnail(url='attachment://bazaar.png')

        await ctx.respond(embed=embed, file=file, ephemeral=True)
        logger.info(f'{h} └──> Bazaar-Sell Query OK')
        return
