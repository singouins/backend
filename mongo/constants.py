# -*- coding: utf8 -*-

# Rarity of Items, Cosmetics, Auctions and Resources
RARITY = [
    'Broken',
    'Common',
    'Uncommon',
    'Rare',
    'Epic',
    'Legendary',
    ]

# Rarity of Creatures and Corpses, with what each rarity implies:
# - xp_mult: XP multiplier of a kill (api/utils/xp.py)
# - spawn_weight: relative odds of the rarity when an Instance spawns its
#   monsters (api/routes/mypc/instance/add.py), out of their total (100)
# - bonus: flat bonuses the rarity gives, one key per use
#   - skinning: added to each resource a Corpse yields (api/.../skinning.py)
# Kept weakest first: models, autocompletes and Discord list them in this order
CREATURE_RARITY = {
    'Small':  {'xp_mult': 0.5, 'spawn_weight': 20,  'bonus': {'skinning': 0}},
    'Medium': {'xp_mult': 1,   'spawn_weight': 50,  'bonus': {'skinning': 1}},
    'Big':    {'xp_mult': 2,   'spawn_weight': 20,  'bonus': {'skinning': 2}},
    'Unique': {'xp_mult': 4,   'spawn_weight': 2.5, 'bonus': {'skinning': 3}},
    'Boss':   {'xp_mult': 8,   'spawn_weight': 5,   'bonus': {'skinning': 4}},
    'God':    {'xp_mult': 16,  'spawn_weight': 2.5, 'bonus': {'skinning': 5}},
    }

# Binding of Items and Cosmetics
ITEM_BIND = [
    'BoA',  # Bind on Account
    'BoE',  # Bind on Equip
    'BoP',  # Bind on Pick Up
    'BoU',  # Bind on Use
    ]
