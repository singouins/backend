# -*- coding: utf8 -*-

import uuid
from unittest.mock import patch

import pytest

from subcommands.singouin.equipment import equipment as equipment_command


@pytest.fixture(autouse=True)
def no_sprite():
    with patch('subcommands.singouin.equipment.creature_sprite', return_value=False):
        yield


async def test_equipment_lists_equipped_and_empty_slots(bot, make_ctx, get_callback, make_creature, make_item):  # noqa: E501
    item = make_item(metatype='armor', metaid=1, rarity='Rare')
    creature = make_creature(
        name='Bobby',
        slots={'head': {'id': item.id, 'metaid': 1, 'metatype': 'armor'}},
        )

    group = bot.create_group(name='mysingouin', description='test')
    equipment_command(group)
    callback = get_callback(group, 'equipment')

    ctx = make_ctx()
    await callback(ctx, str(creature.id))

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    armor_field = embed.fields[0]
    assert 'Test Armor' in armor_field.value
    assert ':no_entry_sign:' in armor_field.value  # the other, unequipped armor slots


async def test_equipment_unknown_creature_responds_once(bot, make_ctx, get_callback):
    group = bot.create_group(name='mysingouin', description='test')
    equipment_command(group)
    callback = get_callback(group, 'equipment')

    ctx = make_ctx()
    await callback(ctx, str(uuid.uuid4()))

    assert ctx.respond.call_count == 1
