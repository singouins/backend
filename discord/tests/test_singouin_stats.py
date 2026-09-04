# -*- coding: utf8 -*-

import uuid
from unittest.mock import patch

import pytest

from subcommands.singouin.stats import stats as stats_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.stats.creature_sprite', return_value=False):
        yield


async def test_stats_displays_base_stats_and_aggro(bot, make_ctx, get_callback, make_creature, make_aggro):  # noqa: E501
    creature = make_creature(
        name='Bobby',
        stats={'race': {}, 'spec': {}, 'total': {'b': 1, 'g': 2, 'm': 3, 'p': 4, 'r': 5, 'v': 6}},
        )
    make_aggro(bearer=creature.id, amount=7)

    group = bot.create_group(name='mysingouin', description='test')
    stats_command(group, bot)
    callback = get_callback(group, 'stats')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert '`7`' in embed.description  # aggro total
    field = embed.fields[0]
    assert '`1`' in field.value
    assert '`6`' in field.value


async def test_stats_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='mysingouin', description='test')
    stats_command(group, bot)
    callback = get_callback(group, 'stats')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
