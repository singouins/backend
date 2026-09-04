# -*- coding: utf8 -*-

import uuid

from mongo.models.Item import ItemDocument
from subcommands.godmode.take import take as take_command


async def test_take_deletes_item_and_responds(bot, make_ctx, get_callback, make_creature, make_item):  # noqa: E501
    creature = make_creature()
    item = make_item(bearer=creature.id, metatype='armor', metaid=1)

    group = bot.create_group(name='godmode', description='test')
    take_command(group)
    callback = get_callback(group, 'take')

    ctx = make_ctx()
    await callback(ctx, str(creature.id), str(item.id))

    assert ctx.respond.call_count == 1
    assert ItemDocument.objects(_id=item.id).count() == 0


async def test_take_unknown_creature_responds_once(bot, make_ctx, get_callback, make_item):
    item = make_item(metatype='armor', metaid=1)

    group = bot.create_group(name='godmode', description='test')
    take_command(group)
    callback = get_callback(group, 'take')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), str(item.id))

    assert ctx.respond.call_count == 1
    # Item must survive an unresolved creature lookup
    assert ItemDocument.objects(_id=item.id).count() == 1


async def test_take_unknown_item_responds_once(bot, make_ctx, get_callback, make_creature):
    creature = make_creature()

    group = bot.create_group(name='godmode', description='test')
    take_command(group)
    callback = get_callback(group, 'take')

    ctx = make_ctx()
    await callback(ctx, str(creature.id), str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
