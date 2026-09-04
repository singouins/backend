# -*- coding: utf8 -*-

import discord

from discord.commands import option
from discord.ext import commands
from loguru import logger

from mongo.models.Creature import CreatureDocument
from mongo.models.Satchel import SatchelDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.singouin._tools import creature_sprite

from variables import AMMO_BULLET, AMMO_SPECIAL, AMMUNITIONS, RESOURCES, SHARDS


def get_wallet_embed_field(bot: discord.Bot, embed: discord.Embed, field_name: str, LIST: list, Satchel: SatchelDocument):  # noqa: E501
    field_value = ''
    DATA = AMMUNITIONS | SHARDS | RESOURCES
    for stuff in LIST:
        emoji = discord.utils.get(bot.emojis, name=DATA[stuff]['emoji'])
        if 'Shard' in field_name:
            field_value += f"> {emoji} : `{getattr(Satchel.shard, stuff, 0): >4}`\n"
        elif 'Resource' in field_name:
            field_value += f"> {emoji} : `{getattr(Satchel.resource, stuff, 0): >4}`\n"
        else:
            field_value += f"> {emoji} : `{getattr(Satchel.ammo, stuff, 0): >4}`\n"
    embed.add_field(name=field_name, value=field_value, inline=True)


def wallet(group_singouin, bot):
    @group_singouin.command(
        description=(
            '[@Singouins role] '
            'Display your Singouin Wallet'
            ),
        default_permission=False,
        name='wallet',
        )
    @commands.has_any_role('Singouins')
    @option(
        "singouinuuid",
        description="Singouin UUID",
        autocomplete=get_mysingouins_list
        )
    async def wallet(
        ctx,
        singouinuuid: str,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_singouin} wallet {singouinuuid}')

        file = None

        try:
            Creature = CreatureDocument.objects(_id=singouinuuid).get()
            Satchel = SatchelDocument.objects(_id=singouinuuid).get()
        except (CreatureDocument.DoesNotExist, SatchelDocument.DoesNotExist):
            msg = 'Singouin NotFound'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Singouin-Wallet Query KO ({msg})')
            return

        try:
            embed = discord.Embed(
                title=Creature.name,
                # description='Profil:',
                colour=discord.Colour.blue()
            )

            get_wallet_embed_field(bot, embed, '**Ammo**', AMMO_BULLET, Satchel)
            get_wallet_embed_field(bot, embed, '**Specials**', AMMO_SPECIAL, Satchel)
            get_wallet_embed_field(bot, embed, '**Shards**', SHARDS, Satchel)

            # We generate Currency field
            if Creature.race in [1, 2, 3, 4]:
                embed.set_footer(text=f"Account balance: {Satchel.currency.banana} 🍌")
            elif Creature.race in [5, 6, 7, 8]:
                embed.set_footer(text=f"Account balance: {Satchel.currency.sausage} 🌭")

            # We check if we have a sprite to add as thumbnail
            if creature_sprite(Creature):
                file = discord.File(f'/tmp/{Creature.id}.png', filename=f'{Creature.id}.png')
                embed.set_thumbnail(url=f'attachment://{Creature.id}.png')
        except Exception as e:
            description = f'Singouin-Wallet Query KO [{e}]'
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
            logger.info(f'{h} └──> Singouin-Wallet Query OK')
            await ctx.respond(embed=embed, ephemeral=True, file=file)
            return
