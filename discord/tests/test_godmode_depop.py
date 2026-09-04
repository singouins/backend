# -*- coding: utf8 -*-

import uuid

import pytest

from mongo.models.Creature import CreatureDocument
from subcommands.godmode.depop import depop as depop_command


async def test_depop_kills_npc_creature_and_removes_it(bot, make_ctx, get_callback, make_creature):  # noqa: E501
    npc = make_creature(account=None)

    group = bot.create_group(name='godmode', description='test')
    depop_command(group)
    callback = get_callback(group, 'depop')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(npc.id))

    assert ctx.respond.call_count == 1
    assert CreatureDocument.objects(_id=npc.id).count() == 0


async def test_depop_unknown_creature_raises_instead_of_responding(bot, make_ctx, get_callback):
    # Documents a real gap: unlike every other godmode command, the
    # Creature lookup here isn't wrapped in a try/except, so an unresolved
    # UUID propagates as an unhandled DoesNotExist instead of a
    # user-facing error embed.
    group = bot.create_group(name='godmode', description='test')
    depop_command(group)
    callback = get_callback(group, 'depop')

    ctx = make_ctx()
    with pytest.raises(CreatureDocument.DoesNotExist):
        await callback(ctx, str(uuid.uuid4()), str(uuid.uuid4()))

    assert ctx.respond.call_count == 0


async def test_depop_player_creature_is_refused_without_responding(bot, make_ctx, get_callback, make_creature):  # noqa: E501
    # Documents a real gap: for a player-owned Creature, the function
    # returns the "refused" embed instead of sending it via
    # ctx.respond(), so the caller never actually sees the refusal.
    player_creature = make_creature(account=uuid.uuid4())

    group = bot.create_group(name='godmode', description='test')
    depop_command(group)
    callback = get_callback(group, 'depop')

    ctx = make_ctx()
    result = await callback(ctx, str(uuid.uuid4()), str(player_creature.id))

    assert result is not None  # the refusal embed, built but never sent
    assert ctx.respond.call_count == 0
    assert CreatureDocument.objects(_id=player_creature.id).count() == 1
