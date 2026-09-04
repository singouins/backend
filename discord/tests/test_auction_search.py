# -*- coding: utf8 -*-

from subcommands.auction.search import search as search_command


async def test_search_by_metatype_finds_match(bot, make_ctx, get_callback, make_auction):
    make_auction(
        item={'id': None, 'metaid': 1, 'metatype': 'armor', 'name': 'Test Armor', 'rarity': 'Common'},  # noqa: E501
        price=15,
        )

    group = bot.create_group(name='auction', description='test')
    search_command(group, bot)
    callback = get_callback(group, 'search')

    ctx = make_ctx()
    await callback(ctx, 'armor', None)

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'Test Armor' in embed.description


async def test_search_no_match_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='auction', description='test')
    search_command(group, bot)
    callback = get_callback(group, 'search')

    ctx = make_ctx()
    await callback(ctx, 'weapon', None)

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'No items were found' in embed.description


async def test_search_by_metatype_and_metaid(bot, make_ctx, get_callback, make_auction):
    make_auction(
        item={'id': None, 'metaid': 1, 'metatype': 'weapon', 'name': 'Test Weapon', 'rarity': 'Rare'},  # noqa: E501
        price=99,
        )

    group = bot.create_group(name='auction', description='test')
    search_command(group, bot)
    callback = get_callback(group, 'search')

    ctx = make_ctx()
    await callback(ctx, 'weapon', '1')

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'Test Weapon' in embed.description
