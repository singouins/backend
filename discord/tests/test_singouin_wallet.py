# -*- coding: utf8 -*-

import uuid
from unittest.mock import patch

import pytest

from subcommands.singouin.wallet import wallet as wallet_command


@pytest.fixture(autouse=True)
def no_sprite():
    # creature_sprite() downloads a real sprite over HTTP and writes to
    # /tmp - none of that belongs in this suite (see scripts/test-local.sh).
    # False is the code's own "no sprite available" outcome, so this just
    # forces the same fallback path the real function takes on failure.
    with patch('subcommands.singouin.wallet.creature_sprite', return_value=False):
        yield


async def test_wallet_shows_banana_balance_for_races_1_to_4(bot, make_ctx, get_callback, make_creature, make_satchel):  # noqa: E501
    creature = make_creature(name='Bobby', race=1)
    make_satchel(_id=creature.id, currency={'banana': 42})

    group = bot.create_group(name='mysingouin', description='test')
    wallet_command(group, bot)
    callback = get_callback(group, 'wallet')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert '42' in embed.footer.text


async def test_wallet_shows_sausage_balance_for_races_5_to_8(bot, make_ctx, get_callback, make_creature, make_satchel):  # noqa: E501
    creature = make_creature(name='Bobby', race=5)
    make_satchel(_id=creature.id, currency={'sausage': 10})

    group = bot.create_group(name='mysingouin', description='test')
    wallet_command(group, bot)
    callback = get_callback(group, 'wallet')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert '10' in embed.footer.text


async def test_wallet_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='mysingouin', description='test')
    wallet_command(group, bot)
    callback = get_callback(group, 'wallet')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
