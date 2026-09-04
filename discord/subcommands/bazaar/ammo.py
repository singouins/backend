# -*- coding: utf8 -*-

import datetime
import discord

from discord.commands import option
from loguru import logger

from mongo.models.Satchel import SatchelDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.bazaar._autocomplete import get_singouin_bazaar_ammo_list

from variables import AMMUNITIONS


def ammo(group_bazaar, bot):
    @group_bazaar.command(
        description='[@Singouins role] Buy/Sell ammunitions to the Bazaar',
        default_permission=False,
        name='ammo',
        )
    @option(
        "singouin_uuid",
        description="Singouin UUID",
        autocomplete=get_mysingouins_list
        )
    @option(
        "action_type",
        description="Bargain Type",
        choices=['Buy', 'Sell']
        )
    @option(
        "caliber",
        description="Caliber",
        autocomplete=get_singouin_bazaar_ammo_list
        )
    async def ammo(
        ctx: discord.ApplicationContext,
        singouin_uuid: str,
        action_type: str,
        caliber: str,
    ):

        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_bazaar} ammo {singouin_uuid} {action_type} {caliber}')

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
            # We get ammunition price (/unit)
            item_price = AMMUNITIONS[caliber]['price']
            item_emoji = discord.utils.get(bot.emojis, name=AMMUNITIONS[caliber]['emoji'])
            embed_desc = f"> {item_emoji} 10x **{caliber.capitalize()}**"

            item_price_total = int(item_price * 10)
            if action_type == 'Sell':
                current_ammo = getattr(Satchel.ammo, caliber, 0)
                if current_ammo < 10:
                    msg = f'Not enough {caliber.capitalize()} in stock (have {current_ammo}, need 10)'  # noqa: E501
                    await ctx.respond(
                        embed=discord.Embed(
                            description=msg,
                            colour=discord.Colour.orange()
                            ),
                        ephemeral=True,
                        )
                    logger.info(f'{h} └──> Bazaar-Sell Query KO ({msg})')
                    return
                # We do the financial transaction
                Satchel.currency.banana += item_price_total
                # We update the Ammunition count
                setattr(Satchel.ammo, caliber, current_ammo - 10)
                embed_title = 'Sold to the Bazaar:'

            elif action_type == 'Buy':
                if Satchel.currency.banana < item_price_total:
                    msg = f'Not enough bananas (have {Satchel.currency.banana}, need {item_price_total})'  # noqa: E501
                    await ctx.respond(
                        embed=discord.Embed(
                            description=msg,
                            colour=discord.Colour.orange()
                            ),
                        ephemeral=True,
                        )
                    logger.info(f'{h} └──> Bazaar-Sell Query KO ({msg})')
                    return
                # We do the financial transaction
                Satchel.currency.banana -= item_price_total
                # We update the Ammunition count
                setattr(Satchel.ammo, caliber, getattr(Satchel.ammo, caliber, 0) + 10)
                embed_title = 'Bought from the Bazaar:'

            Satchel.updated = datetime.datetime.utcnow()
            Satchel.save()
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
            title=embed_title,
            description=embed_desc,
            colour=discord.Colour.green(),
            )
        embed.set_footer(text=f"New Account balance: {Satchel.currency.banana} 🍌")

        # We add Thumbnail
        file = discord.File('/code/resources/bazaar_256x256.png', filename='bazaar.png')
        embed.set_thumbnail(url='attachment://bazaar.png')

        await ctx.respond(embed=embed, file=file, ephemeral=True)
        logger.info(f'{h} └──> Bazaar-Sell Query OK')
        return
