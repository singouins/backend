# -*- coding: utf8 -*-

import uuid

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


async def test_depop_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='godmode', description='test')
    depop_command(group)
    callback = get_callback(group, 'depop')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(uuid.uuid4()))

    assert ctx.respond.call_count == 1


async def test_depop_player_creature_is_refused_and_responds(bot, make_ctx, get_callback, make_creature):  # noqa: E501
    player_creature = make_creature(account=uuid.uuid4())

    group = bot.create_group(name='godmode', description='test')
    depop_command(group)
    callback = get_callback(group, 'depop')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(player_creature.id))

    assert ctx.respond.call_count == 1
    assert CreatureDocument.objects(_id=player_creature.id).count() == 1
