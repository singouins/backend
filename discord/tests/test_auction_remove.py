# -*- coding: utf8 -*-

import uuid

from mongo.models.Auction import AuctionDocument
from subcommands.auction.remove import remove as remove_command


async def test_remove_deletes_auction_and_unlists_item(bot, make_ctx, get_callback, make_creature, make_item, make_auction):  # noqa: E501
    seller = make_creature(name='Seller')
    item = make_item(bearer=seller.id, metatype='armor', metaid=1, auctioned=True)
    auction = make_auction(
        item={'id': item.id, 'metaid': 1, 'metatype': 'armor', 'name': 'Test Armor', 'rarity': 'Common'},  # noqa: E501
        seller={'id': seller.id, 'name': seller.name},
        )

    group = bot.create_group(name='auction', description='test')
    remove_command(group)
    callback = get_callback(group, 'remove')

    ctx = make_ctx()
    await callback(ctx, str(seller.id), 'armor', str(auction.id))

    assert ctx.respond.call_count == 1
    assert AuctionDocument.objects(_id=auction.id).count() == 0
    item.reload()
    assert item.auctioned is False


async def test_remove_unknown_auction_responds_once(bot, make_ctx, get_callback, make_creature):
    seller = make_creature(name='Seller')

    group = bot.create_group(name='auction', description='test')
    remove_command(group)
    callback = get_callback(group, 'remove')

    ctx = make_ctx()
    await callback(ctx, str(seller.id), 'armor', str(uuid.uuid4()))

    assert ctx.respond.call_count == 1


async def test_remove_auction_owned_by_someone_else_is_rejected(bot, make_ctx, get_callback, make_creature, make_item, make_auction):  # noqa: E501
    real_seller = make_creature(name='RealSeller')
    someone_else = make_creature(name='SomeoneElse')
    item = make_item(bearer=real_seller.id, metatype='armor', metaid=1, auctioned=True)
    auction = make_auction(
        item={'id': item.id, 'metaid': 1, 'metatype': 'armor', 'name': 'Test Armor', 'rarity': 'Common'},  # noqa: E501
        seller={'id': real_seller.id, 'name': real_seller.name},
        )

    group = bot.create_group(name='auction', description='test')
    remove_command(group)
    callback = get_callback(group, 'remove')

    ctx = make_ctx()
    await callback(ctx, str(someone_else.id), 'armor', str(auction.id))

    assert ctx.respond.call_count == 1
    assert AuctionDocument.objects(_id=auction.id).count() == 1
