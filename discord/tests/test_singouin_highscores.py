# -*- coding: utf8 -*-

import uuid
from unittest.mock import patch

import pytest
from mongoengine.errors import DoesNotExist

from subcommands.singouin.highscores import highscores as highscores_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.highscores.creature_sprite', return_value=False):
        yield


async def test_highscores_displays_fields(bot, make_ctx, get_callback, make_creature, make_highscore):  # noqa: E501
    creature = make_creature(name='Bobby')
    highscore = make_highscore(_id=creature.id)
    highscore.internal.item.sold = 3
    highscore.save()

    group = bot.create_group(name='mysingouin', description='test')
    highscores_command(group, bot)
    callback = get_callback(group, 'highscores')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    field_names = [f.name for f in embed.fields]
    assert any('General' in name for name in field_names)
    assert not any('Internal' in name for name in field_names)  # explicitly skipped


async def test_highscores_unknown_creature_raises_instead_of_responding(bot, make_ctx, get_callback):  # noqa: E501
    # Documents a real gap: like wallet.py/stats.py, the Creature and
    # Highscore lookups aren't wrapped in a try/except, so an unresolved
    # UUID propagates as an unhandled DoesNotExist instead of a
    # user-facing error embed.
    group = bot.create_group(name='mysingouin', description='test')
    highscores_command(group, bot)
    callback = get_callback(group, 'highscores')

    ctx = make_ctx()
    with pytest.raises(DoesNotExist):
        await callback(ctx, str(uuid.uuid4()))

    assert ctx.respond.call_count == 0
