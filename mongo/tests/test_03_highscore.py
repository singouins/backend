# -*- coding: utf8 -*-

import os
import sys
import uuid

# Needed for local imports and simulate production paths
LOCAL_PATH = os.path.dirname(os.path.abspath('mongo'))
sys.path.append(LOCAL_PATH)

from mongo.models.Highscore import (  # noqa: E402
    HighscoreDocument,
    HighscoreGeneral,
    HighscoreInternal,
    HighscoreInternalConsumable,
    HighscoreInternalCurrency,
    HighscoreInternalGenericResource,
    HighscoreInternalShard,
    HighscoreProfession,
)
from mongo.utils import utcnow  # noqa: E402

CREATURE_NAME = 'PyTest Creature'
CREATURE_ID = str(uuid.uuid3(uuid.NAMESPACE_DNS, CREATURE_NAME))


def test_mongodb_highscore_new():
    """
    Creating a new HighscoreDocument
    """

    newHighscore = HighscoreDocument(
        _id=CREATURE_ID,
        general=HighscoreGeneral(),
        internal=HighscoreInternal(
            consumable=HighscoreInternalConsumable(),
            currency=HighscoreInternalCurrency(),
            fur=HighscoreInternalGenericResource(),
            item=HighscoreInternalGenericResource(),
            leather=HighscoreInternalGenericResource(),
            meat=HighscoreInternalGenericResource(),
            ore=HighscoreInternalGenericResource(),
            shard=HighscoreInternalShard(),
            skin=HighscoreInternalGenericResource(),
            ),
        profession=HighscoreProfession(),
    )
    newHighscore.save()

    assert str(newHighscore.id) == CREATURE_ID
    assert newHighscore.general.kill == 0
    assert newHighscore.general.assist == 0
    assert newHighscore.general.xp == 0
    # Internal counters start at zero: shards by rarity, consumables created,
    # currency spent
    internal = HighscoreDocument.objects(_id=CREATURE_ID).get().internal
    assert internal.shard.broken.used == 0
    assert internal.shard.legendary.obtained == 0
    assert internal.consumable.health.fast.created == 0
    assert internal.currency.spent == 0
    stored = HighscoreDocument._get_collection().find_one({'_id': CREATURE_ID})
    assert set(stored['internal']['shard']) == {
        'broken', 'common', 'uncommon', 'rare', 'epic', 'legendary',
        }
    assert stored['internal']['shard']['rare'] == {
        'bought': 0, 'obtained': 0, 'recycled': 0, 'sold': 0, 'used': 0,
        }
    assert stored['internal']['consumable'] == {
        'health': {'base': {'created': 0}, 'fast': {'created': 0}, 'long': {'created': 0}},
        }
    assert stored['internal']['currency'] == {'spent': 0}
    assert stored['general'] == {'assist': 0, 'death': 0, 'kill': 0, 'xp': 0}

    #
    # Update
    #

    highscores_update_query = {
        'inc__general__kill': 10,
        'inc__general__assist': 3,
        'inc__general__xp': 450,
        "set__updated": utcnow(),
        }
    newHighscore.update(**highscores_update_query)


def test_mongodb_highscore_get():
    """
    Querying a HighscoreDocument
    """
    Highscore = HighscoreDocument.objects(_id=CREATURE_ID).get()

    assert Highscore.general.kill == 10
    assert Highscore.general.assist == 3
    assert Highscore.general.xp == 450


def test_mongodb_highscore_search():
    """
    Searching a HighscoreDocument
    """
    assert HighscoreDocument.objects(_id=CREATURE_ID).count() == 1


def test_mongodb_highscore_del():
    """
    Removing a HighscoreDocument
    """

    HighscoreDocument.objects(_id=CREATURE_ID).delete()

    assert HighscoreDocument.objects(_id=CREATURE_ID).count() == 0
