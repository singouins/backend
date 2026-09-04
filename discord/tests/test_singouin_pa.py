# -*- coding: utf8 -*-

import uuid
from unittest.mock import patch

import pytest

from subcommands.singouin.pa import pa as pa_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.pa.creature_sprite', return_value=False):
        yield


@pytest.fixture(autouse=True)
def pa_stub():
    # get_pa() reads TTLs from a live Redis - this suite deliberately runs
    # without one (see scripts/test-local.sh), so stub in canned PA data
    # instead of the real utils.redis.get_pa.
    canned = {
        'red': {'pa': 16, 'ttnpa': 0, 'ttl': -1},
        'blue': {'pa': 8, 'ttnpa': 0, 'ttl': -1},
        }
    with patch('subcommands.singouin.pa.get_pa', return_value=canned) as stub:
        yield stub


async def test_pa_displays_bars(bot, make_ctx, get_callback, make_creature, pa_stub):
    creature = make_creature(name='Bobby')

    group = bot.create_group(name='mysingouin', description='test')
    pa_command(group)
    callback = get_callback(group, 'pa')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    pa_stub.assert_called_once_with(creatureuuid=str(creature.id))
    embed = ctx.respond.call_args.kwargs['embed']
    field = embed.fields[0]
    assert '(16/16)' in field.value
    assert '(8/8)' in field.value


async def test_pa_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='mysingouin', description='test')
    pa_command(group)
    callback = get_callback(group, 'pa')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
