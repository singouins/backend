# -*- coding: utf8 -*-

from subcommands.singouin.show import show as show_command


async def test_show_lists_users_creatures(bot, make_ctx, get_callback, make_user, make_creature):
    user = make_user(discord={'name': 'tester', 'ack': True})
    make_creature(account=user.id, name='Bobby', race=1, level=3)

    group = bot.create_group(name='mysingouin', description='test')
    show_command(group, bot)
    callback = get_callback(group, 'show')

    ctx = make_ctx(author_name='tester')
    await callback(ctx)

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'Bobby' in embed.description
    assert 'Level:3' in embed.description


async def test_show_unknown_discord_user_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='mysingouin', description='test')
    show_command(group, bot)
    callback = get_callback(group, 'show')

    ctx = make_ctx(author_name='not-in-db')
    await callback(ctx)

    assert ctx.respond.call_count == 1
