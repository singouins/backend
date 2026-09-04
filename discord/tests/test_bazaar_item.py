# -*- coding: utf8 -*-

import uuid

from subcommands.bazaar.item import item as item_command


async def test_sell_updates_balance_and_highscore(bot, make_ctx, get_callback, make_satchel, make_highscore, make_item):  # noqa: E501
    singouin_id = uuid.uuid4()
    satchel = make_satchel(_id=singouin_id)
    highscore = make_highscore(_id=singouin_id)
    # size 2x2, tier 1, rarity Rare (index 3): 2*2 * (1+1) * 3 // 2 == 12
    itm = make_item(bearer=singouin_id, metatype='armor', metaid=1, rarity='Rare')

    group = bot.create_group(name='bazaar', description='test')
    item_command(group, bot)
    callback = get_callback(group, 'item')

    ctx = make_ctx()
    await callback(ctx, str(singouin_id), 'Sell', str(itm.id))

    assert ctx.respond.call_count == 1

    satchel.reload()
    highscore.reload()
    itm.reload()

    assert satchel.currency.banana == 12
    assert highscore.internal.item.sold == 1
    # Sold items are shelved back onto the house account
    assert str(itm.bearer) == '00000000-cafe-cafe-cafe-000000000000'


async def test_sell_unknown_item_leaves_state_untouched(bot, make_ctx, get_callback, make_satchel, make_highscore):  # noqa: E501
    singouin_id = uuid.uuid4()
    satchel = make_satchel(_id=singouin_id)
    make_highscore(_id=singouin_id)

    group = bot.create_group(name='bazaar', description='test')
    item_command(group, bot)
    callback = get_callback(group, 'item')

    ctx = make_ctx()
    await callback(ctx, str(singouin_id), 'Sell', str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
    satchel.reload()
    assert satchel.currency.banana == 0
