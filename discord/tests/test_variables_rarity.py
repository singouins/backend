# -*- coding: utf8 -*-

from mongo.constants import CREATURE_RARITY
from variables import rarity_monster_types_discord, rarity_monster_types_emoji


def test_every_creature_rarity_has_its_emoji_and_discord_tag():
    # Keyed by name: a rarity added to CREATURE_RARITY without its colours
    # fails here, not as a KeyError in /godmode pop
    assert set(rarity_monster_types_emoji) == set(CREATURE_RARITY)
    assert set(rarity_monster_types_discord) == set(CREATURE_RARITY)
