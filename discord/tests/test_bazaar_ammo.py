# -*- coding: utf8 -*-

import uuid

from subcommands.bazaar.ammo import ammo as ammo_command


async def test_sell_updates_balance_and_ammo_count(bot, make_ctx, get_callback, make_satchel):
    singouin_id = uuid.uuid4()
    satchel = make_satchel(_id=singouin_id, ammo={'cal22': 20}, currency={'banana': 0})

    group = bot.create_group(name='bazaar', description='test')
    ammo_command(group, bot)
    callback = get_callback(group, 'ammo')

    ctx = make_ctx()
    await callback(ctx, str(singouin_id), 'Sell', 'cal22')

    assert ctx.respond.call_count == 1
    satchel.reload()
    # price 0.1/unit * 10 units == 1
    assert satchel.currency.banana == 1
    assert satchel.ammo.cal22 == 10


async def test_buy_updates_balance_and_ammo_count(bot, make_ctx, get_callback, make_satchel):
    singouin_id = uuid.uuid4()
    satchel = make_satchel(_id=singouin_id, ammo={'cal22': 0}, currency={'banana': 100})

    group = bot.create_group(name='bazaar', description='test')
    ammo_command(group, bot)
    callback = get_callback(group, 'ammo')

    ctx = make_ctx()
    await callback(ctx, str(singouin_id), 'Buy', 'cal22')

    assert ctx.respond.call_count == 1
    satchel.reload()
    assert satchel.currency.banana == 99
    assert satchel.ammo.cal22 == 10


async def test_satchel_not_found_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='bazaar', description='test')
    ammo_command(group, bot)
    callback = get_callback(group, 'ammo')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), 'Sell', 'cal22')

    assert ctx.respond.call_count == 1


async def test_buy_with_insufficient_balance_goes_negative(bot, make_ctx, get_callback, make_satchel):  # noqa: E501
    # Documents a real gap: there is no balance check on the 'Buy' path, so
    # a purchase the account can't afford still goes through and leaves a
    # negative currency balance instead of being rejected.
    singouin_id = uuid.uuid4()
    satchel = make_satchel(_id=singouin_id, ammo={'cal22': 0}, currency={'banana': 0})

    group = bot.create_group(name='bazaar', description='test')
    ammo_command(group, bot)
    callback = get_callback(group, 'ammo')

    ctx = make_ctx()
    await callback(ctx, str(singouin_id), 'Buy', 'cal22')

    assert ctx.respond.call_count == 1
    satchel.reload()
    assert satchel.currency.banana == -1


async def test_sell_more_than_owned_goes_negative(bot, make_ctx, get_callback, make_satchel):
    # Documents a real gap: there is no stock check on the 'Sell' path, so
    # selling ammunition the account doesn't have still goes through and
    # leaves a negative ammo count instead of being rejected.
    singouin_id = uuid.uuid4()
    satchel = make_satchel(_id=singouin_id, ammo={'cal22': 0}, currency={'banana': 0})

    group = bot.create_group(name='bazaar', description='test')
    ammo_command(group, bot)
    callback = get_callback(group, 'ammo')

    ctx = make_ctx()
    await callback(ctx, str(singouin_id), 'Sell', 'cal22')

    assert ctx.respond.call_count == 1
    satchel.reload()
    assert satchel.ammo.cal22 == -10
