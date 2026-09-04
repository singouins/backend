# -*- coding: utf8 -*-

import os

from loguru import logger

from mongo.models.Meta import MetaArmor, MetaRace, MetaWeapon


def str2bool(value: str) -> bool:
    _MAP = {
        'true': True,
        'on': True,
        'false': False,
        'off': False
    }
    try:
        return _MAP[str(value).lower()]
    except KeyError:
        raise ValueError('"{}" is not a valid bool value'.format(value))


# Grab the environment variables
env_vars = {
    "API_ENV": os.environ.get("API_ENV", None),
    "DISCORD_GUILD": os.environ.get("DISCORD_GUILD", None),
    "DISCORD_TOKEN": os.environ.get("DISCORD_TOKEN"),
    "PS_DISCORD": os.environ.get("PS_DISCORD", f'dc-broadcast-{os.environ.get("API_ENV", None).lower()}'),  # noqa: E501
    "REDIS_HOST": os.environ.get("REDIS_HOST", '127.0.0.1'),
    "REDIS_PORT": int(os.environ.get("REDIS_PORT", 6379)),
    "REDIS_BASE": int(os.environ.get("REDIS_BASE", 0)),
    "SSL_CHECK": str2bool(os.getenv("SSL_CHECK", "True")),
    "SSL_TARGET_HOST": os.environ.get("SSL_TARGET_HOST"),
    "SSL_TARGET_PORT": os.environ.get("SSL_TARGET_PORT", 443),
    "SSL_CHANNEL": os.environ.get("SSL_CHANNEL"),
    "URL_ASSETS": os.environ.get("URL_ASSETS", 'https://singouins.github.io/assets'),
    "YQ_DISCORD": os.environ.get("YQ_DISCORD", f'{os.environ.get("API_ENV", None)}:yarqueue:discord'), # noqa E501
    "YQ_CHECK": str2bool(os.getenv("YQ_CHECK", "False")),
}
# Print the environment variables for debugging
_SENSITIVE_VARS = {"DISCORD_TOKEN"}
for var, value in env_vars.items():
    if var in _SENSITIVE_VARS and value is not None:
        value = f'{value[:4]}...{value[-4:]}'
    logger.debug(f"{var}: {value}")


"""
DISCLAIMER: This is some fat shit I dumped here

This is a HUGE Dictionary to manipulate pore easiliy all the metas
Without having to query MongoDB all the time internally

Do not modifiy unless you're ready for consequences
"""
metaNames = {
    'armor': [doc.to_mongo().to_dict() for doc in MetaArmor.objects()],
    'weapon': [doc.to_mongo().to_dict() for doc in MetaWeapon.objects()],
    'race': [doc.to_mongo().to_dict() for doc in MetaRace.objects()]
}
metaIndexed = {
    'armor': {armor["_id"]: armor for armor in metaNames['armor']},
    'weapon': {weapon["_id"]: weapon for weapon in metaNames['weapon']},
    'race': {race["_id"]: race for race in metaNames['race']},
}

# Rarities Emojis, Discord tags, and color integers
rarity_emoji = ['🟤 ', '⚪ ', '🟢 ', '🔵 ', '🟣 ', '🟠 ']
rarity_discord = [':brown_square:', ':white_large_square:', ':green_square:', ':blue_square:', ':purple_square:', ':orange_square:']  # noqa: E501
rarity_integer = [10197915, 16777215, 8311585, 4886754, 9442302, 16098851]

# Rarity dictionnaries for Items
RARITY_ITEM = ['Broken', 'Common', 'Uncommon', 'Rare', 'Epic', 'Legendary']
rarity_item_types_emoji = dict(zip(RARITY_ITEM, rarity_emoji))
rarity_item_types_discord = dict(zip(RARITY_ITEM, rarity_discord))
rarity_item_types_integer = dict(zip(RARITY_ITEM, rarity_integer))

# Rarity dictionnaries for Monsters
rarity_monster = ['Small', 'Medium', 'Big', 'Unique', 'Boss', 'God']
rarity_monster_types_emoji = dict(zip(rarity_monster, rarity_emoji))
rarity_monster_types_discord = dict(zip(rarity_monster, rarity_discord))

item_types_discord = {
    'armor': ':shirt:',
    'weapon': ':dagger:'
    }

slots_armor = {
    'head': ':military_helmet:',
    'shoulders': ':mechanical_arm:',
    'torso': ':shirt:',
    'hands': ':hand_splayed:',
    'legs': ':mechanical_leg:',
    'feet': ':athletic_shoe:',
    }
slots_weapon = {
    'holster': ':school_satchel:',
    'lefthand': ':left_fist:',
    'righthand': ':right_fist:',
}
slots_types = slots_armor | slots_weapon  # Merge the dicts into one

#
# Ammunition CONSTANTS
#
AMMO_BULLET = {
    'cal22':   {'price': 0.1, 'emoji': 'ammoCal22'},
    'cal223':  {'price': 0.3, 'emoji': 'ammoCal223'},
    'cal311':  {'price': 0.5, 'emoji': 'ammoCal311'},
    'cal50':   {'price': 1,   'emoji': 'ammoCal50'},
    'cal55':   {'price': 2,   'emoji': 'ammoCal55'},
}
AMMO_SPECIAL = {
    'arrow':   {'price': 1,   'emoji': 'ammoArrow'},
    'bolt':    {'price': 1,   'emoji': 'ammoBolt'},
    'fuel':    {'price': 1,   'emoji': 'ammoFuel'},
    'grenade': {'price': 1,   'emoji': 'ammoGrenade'},
    'rocket':  {'price': 1,   'emoji': 'ammoRocket'},
    'shell':   {'price': 1,   'emoji': 'ammoShell'},
}
AMMUNITIONS = AMMO_BULLET | AMMO_SPECIAL   # Merge the dicts into one

#
# Shards CONSTANTS
#
SHARDS = {
    'Broken':    {'price': 1,   'emoji': 'shardBroken'},
    'Common':    {'price': 1,   'emoji': 'shardCommon'},
    'Uncommon':  {'price': 1,   'emoji': 'shardUncommon'},
    'Rare':      {'price': 1,   'emoji': 'shardRare'},
    'Epic':      {'price': 1,   'emoji': 'shardEpic'},
    'Legendary': {'price': 1,   'emoji': 'shardLegendary'},
}

#
# Resources CONSTANTS
#
RESOURCES = {
    'Fur':     {'price': 1,   'emoji': 'shardBroken'},
    'Leather': {'price': 1,   'emoji': 'shardCommon'},
    'Meat':    {'price': 1,   'emoji': 'cut_of_meat'},
    'Skin':    {'price': 1,   'emoji': 'shardRare'},
}
