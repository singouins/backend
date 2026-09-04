# -*- coding: utf8 -*-

import uuid

from subcommands.auction.buy import buy as buy_command


async def test_buy_presents_confirmation_view(bot, make_ctx, get_callback):
    # /auction buy itself does no Mongo work - it just presents a
    # confirmation view whose buttons (buyView, see _view.py) do the real
    # purchase logic. See test_auction_buy_view.py for that.
    group = bot.create_group(name='auction', description='test')
    buy_command(group)
    callback = get_callback(group, 'buy')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), 'armor', str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
    assert ctx.respond.call_args.kwargs['view'] is not None
