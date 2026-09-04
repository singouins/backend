# -*- coding: utf8 -*-

import uuid

from mongo.models.Creature import CreatureDocument
from subcommands.godmode.pop import pop as pop_command


async def test_pop_spawns_creature_from_meta_race(bot, make_ctx, get_callback, make_instance):
    instance = make_instance()

    group = bot.create_group(name='godmode', description='test')
    pop_command(group)
    callback = get_callback(group, 'pop')

    ctx = make_ctx()
    await callback(ctx, 1, str(instance.id), 'Medium', 3, 3)

    assert ctx.respond.call_count == 1
    creature = CreatureDocument.objects(name='Test Monster').first()
    assert creature is not None
    assert creature.account is None
    assert str(creature.instance) == str(instance.id)
    assert creature.stats.total.b == 1
    assert creature.hp.max == 3 + 100  # meta min_m (3) + 100, per pop.py


async def test_pop_unknown_instance_responds_with_nothing(bot, make_ctx, get_callback):
    # Current behavior: an unresolved instance is only logged, not
    # reported back to the caller - the interaction is left hanging
    # rather than getting an error embed like every other godmode command.
    group = bot.create_group(name='godmode', description='test')
    pop_command(group)
    callback = get_callback(group, 'pop')

    ctx = make_ctx()
    result = await callback(ctx, 1, str(uuid.uuid4()), 'Medium', 3, 3)

    assert result is None
    assert ctx.respond.call_count == 0
    assert CreatureDocument.objects.count() == 0
