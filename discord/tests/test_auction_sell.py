# -*- coding: utf8 -*-

import uuid

from mongo.models.Auction import AuctionDocument
from subcommands.auction.sell import sell as sell_command


async def test_sell_lists_item_and_marks_it_auctioned(bot, make_ctx, get_callback, make_creature, make_item):  # noqa: E501
    seller = make_creature(name='Seller')
    item = make_item(bearer=seller.id, metatype='armor', metaid=1, bound_type='BoE', auctioned=False)  # noqa: E501

    group = bot.create_group(name='auction', description='test')
    sell_command(group)
    callback = get_callback(group, 'sell')

    ctx = make_ctx()
    await callback(ctx, str(seller.id), str(item.id), 42)

    assert ctx.respond.call_count == 1
    auction = AuctionDocument.objects.first()
    assert auction is not None
    assert auction.price == 42
    assert auction.item.id == item.id
    assert auction.seller.id == seller.id
    item.reload()
    assert item.auctioned is True


async def test_sell_unknown_seller_responds_once(bot, make_ctx, get_callback, make_item):
    item = make_item(metatype='armor', metaid=1, bound_type='BoE', auctioned=False)

    group = bot.create_group(name='auction', description='test')
    sell_command(group)
    callback = get_callback(group, 'sell')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(item.id), 42)

    assert ctx.respond.call_count == 1
    assert AuctionDocument.objects.count() == 0


async def test_sell_bop_item_is_rejected(bot, make_ctx, get_callback, make_creature, make_item):
    # BoP items can't be listed - only the auctioned=False/bound_type='BoE'
    # combination matches.
    seller = make_creature(name='Seller')
    item = make_item(bearer=seller.id, metatype='armor', metaid=1, bound_type='BoP', auctioned=False)  # noqa: E501

    group = bot.create_group(name='auction', description='test')
    sell_command(group)
    callback = get_callback(group, 'sell')

    ctx = make_ctx()
    await callback(ctx, str(seller.id), str(item.id), 42)

    assert ctx.respond.call_count == 1
    assert AuctionDocument.objects.count() == 0
    item.reload()
    assert item.auctioned is False
