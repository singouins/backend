# -*- coding: utf8 -*-

from subcommands.auction.show import show as show_command


async def test_show_lists_sellers_auctions(bot, make_ctx, get_callback, make_creature, make_auction):  # noqa: E501
    seller = make_creature(name='Seller')
    make_auction(
        item={'id': seller.id, 'metaid': 1, 'metatype': 'armor', 'name': 'Test Armor', 'rarity': 'Common'},  # noqa: E501
        price=15,
        seller={'id': seller.id, 'name': seller.name},
        )

    group = bot.create_group(name='auction', description='test')
    show_command(group, bot)
    callback = get_callback(group, 'show')

    ctx = make_ctx()
    await callback(ctx, str(seller.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert '(1):' in embed.title
    assert 'Test Armor' in embed.description


async def test_show_no_auctions_responds_once(bot, make_ctx, get_callback, make_creature):
    seller = make_creature(name='Seller')

    group = bot.create_group(name='auction', description='test')
    show_command(group, bot)
    callback = get_callback(group, 'show')

    ctx = make_ctx()
    await callback(ctx, str(seller.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'not selling anything' in embed.description
