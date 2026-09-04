# -*- coding: utf8 -*-

import uuid
from unittest.mock import patch

import pytest

from subcommands.singouin.inventory import inventory as inventory_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.inventory.creature_sprite', return_value=False):
        yield


async def test_inventory_lists_unequipped_unauctioned_items(bot, make_ctx, get_callback, make_creature, make_item):  # noqa: E501
    creature = make_creature(name='Bobby')
    make_item(bearer=creature.id, metatype='armor', metaid=1, rarity='Common', bound_type='BoP')
    make_item(bearer=creature.id, metatype='armor', metaid=1, offsetx=1, offsety=1)  # equipped
    make_item(bearer=creature.id, metatype='armor', metaid=1, auctioned=True)  # listed

    group = bot.create_group(name='mysingouin', description='test')
    inventory_command(group)
    callback = get_callback(group, 'inventory')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    field = embed.fields[0]
    assert field.value.count('Test Armor') == 1


async def test_inventory_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='mysingouin', description='test')
    inventory_command(group)
    callback = get_callback(group, 'inventory')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
