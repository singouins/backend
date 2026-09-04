# -*- coding: utf8 -*-

from unittest.mock import patch

import pytest

from subcommands.singouin.korp import korp as korp_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.korp.creature_sprite', return_value=False):
        yield


async def test_korp_displays_members(bot, make_ctx, get_callback, make_creature, make_korp):
    a_korp = make_korp(name='The Korp')
    leader = make_creature(name='Leader', korp={'id': a_korp.id, 'rank': 'leader'})
    a_korp.leader = leader.id
    a_korp.save()

    group = bot.create_group(name='mysingouin', description='test')
    korp_command(group, bot)
    callback = get_callback(group, 'korp')

    ctx = make_ctx()
    await callback(ctx, str(leader.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'The Korp' in embed.title
    assert 'Leader' in embed.description
    assert leader.name in embed.description


async def test_korp_not_in_a_korp_responds_once(bot, make_ctx, get_callback, make_creature):
    creature = make_creature(name='Loner')

    group = bot.create_group(name='mysingouin', description='test')
    korp_command(group, bot)
    callback = get_callback(group, 'korp')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'not in a Korp' in embed.description
