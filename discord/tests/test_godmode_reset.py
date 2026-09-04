# -*- coding: utf8 -*-

import uuid
from unittest.mock import MagicMock, patch

import pytest

from subcommands.godmode.reset import reset as reset_command


@pytest.fixture
def redis_stub():
    # reset.py's Redis usage (clearing cached PA keys) is a side effect
    # unrelated to what these tests assert - this suite deliberately runs
    # without a live Redis (see scripts/test-local.sh), so this stub
    # stands in for utils.redis.r rather than pulling in a real service.
    stub = MagicMock()
    stub.exists.return_value = True
    with patch('subcommands.godmode.reset.r', stub):
        yield stub


async def test_reset_clears_pa_keys_and_responds(bot, make_ctx, get_callback, make_creature, redis_stub):  # noqa: E501
    creature = make_creature()

    group = bot.create_group(name='godmode', description='test')
    reset_command(group)
    callback = get_callback(group, 'reset')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(creature.id))

    assert ctx.respond.call_count == 1
    assert redis_stub.delete.call_count == 2  # blue + red


async def test_reset_unknown_singouin_responds_once(bot, make_ctx, get_callback, redis_stub):
    group = bot.create_group(name='godmode', description='test')
    reset_command(group)
    callback = get_callback(group, 'reset')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
    assert redis_stub.delete.call_count == 0
