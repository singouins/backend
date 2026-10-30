# -*- coding: utf8 -*-

import discord

from loguru import logger

from mongo.constants import RARITY
from mongo.models.Item import ItemDocument
from mongo.models.Satchel import SatchelDocument

from variables import AMMUNITIONS, metaIndexed, rarity_item_types_emoji as rite


async def get_singouin_bazaar_ammo_list(ctx: discord.AutocompleteContext):
    # Pre-flight check
    db_list = []

    # We check if we are going to sell, or to buy
    if ctx.options['action_type'] == 'Sell':
        try:
            Satchel = SatchelDocument.objects(_id=ctx.options['singouin_uuid']).get()
        except SatchelDocument.DoesNotExist:
            logger.debug("SatchelDocument Query KO (404)")
        except Exception as e:
            logger.error(f'MongoDB Query KO [{e}]')

        try:
            for ammo_cal, ammo_info in AMMUNITIONS.items():
                ammo_stock = getattr(Satchel.ammo, ammo_cal)
                if ammo_stock >= 10:
                    item_name = ammo_cal.capitalize()
                    item_price = ammo_info['price']
                    db_list.append(discord.OptionChoice(f"💥 10x {item_name} ({item_price}/u) [{ammo_stock}]", value=ammo_cal))  # noqa: E501
        except Exception as e:
            logger.error(f'AMMUNITIONS Query KO [{e}]')
        else:
            return db_list
    else:
        try:
            for ammo_cal, ammo_info in AMMUNITIONS.items():
                ammo_stock = '∞'  # Bazaar has unlimited stock for now
                item_name = ammo_cal.capitalize()
                item_price = ammo_info['price']
                db_list.append(discord.OptionChoice(f"💥 10x {item_name} ({item_price}/u) [{ammo_stock}]", value=ammo_cal))  # noqa: E501
        except Exception as e:
            logger.error(f'AMMUNITIONS Query KO [{e}]')
        else:
            return db_list


async def get_singouin_saleable_item_list(ctx: discord.AutocompleteContext):
    # Pre-flight check
    db_list = []
    try:
        Items = ItemDocument.objects(auctioned=False, bearer=ctx.options['singouin_uuid'])
    except Exception as e:
        logger.error(f'MongoDB Query KO [{e}]')
    else:
        if len(Items) == 0:
            msg = 'Item NotFound or not matching criterias'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'Query KO ({msg})')
            return db_list

    # Real stuff
    for Item in Items:
        eh = rite[Item.rarity]

        meta = metaIndexed[Item.metatype][Item.metaid]
        sizex, sizey = map(int, meta['size'].split("x"))

        item_name = meta['name']
        item_price = sizex * sizey * (meta['tier'] + 1) * RARITY.index(Item.rarity) // 2
        db_list.append(discord.OptionChoice(f"{eh} {item_name} ({item_price})", value=str(Item.id)))  # noqa: E501

    return db_list
