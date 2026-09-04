# -*- coding: utf8 -*-

import uuid

from mongo.models.Item import ItemDocument
from subcommands.godmode.give import give as give_command


async def test_give_creates_armor_item_for_creature(bot, make_ctx, get_callback, make_creature):
    creature = make_creature()

    group = bot.create_group(name='godmode', description='test')
    give_command(group)
    callback = get_callback(group, 'give')

    ctx = make_ctx()
    await callback(ctx, str(creature.id), 'Rare', 'armor', 1, 'BoP')

    assert ctx.respond.call_count == 1
    items = ItemDocument.objects(bearer=creature.id)
    assert items.count() == 1
    assert items.first().metatype == 'armor'
    assert items.first().metaid == 1
    assert items.first().bound is True


async def test_give_creates_unbound_item_for_boe(bot, make_ctx, get_callback, make_creature):
    creature = make_creature()

    group = bot.create_group(name='godmode', description='test')
    give_command(group)
    callback = get_callback(group, 'give')

    ctx = make_ctx()
    await callback(ctx, str(creature.id), 'Common', 'weapon', 1, 'BoE')

    assert ctx.respond.call_count == 1
    item = ItemDocument.objects(bearer=creature.id).first()
    assert item.bound is False
    assert item.ammo == 30  # from the seeded Test Weapon's max_ammo


async def test_give_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='godmode', description='test')
    give_command(group)
    callback = get_callback(group, 'give')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()), 'Rare', 'armor', 1, 'BoP')

    assert ctx.respond.call_count == 1
    assert ItemDocument.objects.count() == 0
