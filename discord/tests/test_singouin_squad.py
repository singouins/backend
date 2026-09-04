# -*- coding: utf8 -*-

from unittest.mock import patch

import pytest

from subcommands.singouin.squad import squad as squad_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.squad.creature_sprite', return_value=False):
        yield


async def test_squad_displays_members(bot, make_ctx, get_callback, make_creature, make_squad):
    a_squad = make_squad()
    leader = make_creature(name='Leader', squad={'id': a_squad.id, 'rank': 'leader'})
    a_squad.leader = leader.id
    a_squad.save()

    group = bot.create_group(name='mysingouin', description='test')
    squad_command(group, bot)
    callback = get_callback(group, 'squad')

    ctx = make_ctx()
    await callback(ctx, str(leader.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'Leader' in embed.description
    assert leader.name in embed.description


async def test_squad_members_are_sorted_by_rank(bot, make_ctx, get_callback, make_creature, make_squad):  # noqa: E501
    # Regression test: SquadMembers.order_by(...) used to be called
    # without reassigning its result, so it had no effect (mongoengine
    # querysets are immutable - order_by() returns a new queryset rather
    # than sorting in place). Member order must now follow squad.rank.
    a_squad = make_squad()
    zebra = make_creature(name='Zebra', squad={'id': a_squad.id, 'rank': 'z-member'})
    alice = make_creature(name='Alice', squad={'id': a_squad.id, 'rank': 'a-member'})
    a_squad.leader = alice.id
    a_squad.save()

    group = bot.create_group(name='mysingouin', description='test')
    squad_command(group, bot)
    callback = get_callback(group, 'squad')

    ctx = make_ctx()
    await callback(ctx, str(zebra.id))

    embed = ctx.respond.call_args.kwargs['embed']
    assert embed.description.index('Alice') < embed.description.index('Zebra')


async def test_squad_not_in_a_squad_responds_once(bot, make_ctx, get_callback, make_creature):
    creature = make_creature(name='Loner')

    group = bot.create_group(name='mysingouin', description='test')
    squad_command(group, bot)
    callback = get_callback(group, 'squad')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'not in a Squad' in embed.description
