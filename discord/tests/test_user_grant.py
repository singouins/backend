# -*- coding: utf8 -*-

from subcommands.user.grant import grant as grant_command


async def test_grant_responds_once_regardless_of_creature_count(bot, make_ctx, get_callback, make_user, make_creature):  # noqa: E501
    # Regression test: the success response used to live inside the
    # `for Creature in Creatures` loop, so a user with 2+ creatures would
    # trigger a second ctx.respond() and blow up on an already-acknowledged
    # interaction. It must fire exactly once, after the loop.
    user = make_user(discord={'name': 'tester', 'ack': False})
    make_creature(account=user.id)
    make_creature(account=user.id)

    group = bot.create_group(name='user', description='test')
    grant_command(group, bot)
    callback = get_callback(group, 'grant')

    ctx = make_ctx(author_name='tester')
    await callback(ctx)

    assert ctx.respond.call_count == 1


async def test_grant_unknown_discord_user_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='user', description='test')
    grant_command(group, bot)
    callback = get_callback(group, 'grant')

    ctx = make_ctx(author_name='not-in-db')
    await callback(ctx)

    assert ctx.respond.call_count == 1
