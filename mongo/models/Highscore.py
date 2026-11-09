
from mongoengine import (
    Document,
    EmbeddedDocument,
    )
from mongoengine.fields import (
    DateTimeField,
    EmbeddedDocumentField,
    IntField,
    # DictField,
    # ListField,
    # StringField,
    UUIDField,
)

from mongo.utils import utcnow

#
# Collection: highscore
#


class HighscoreInternalGenericResource(EmbeddedDocument):
    """
    Define the embedded document for:
    - Highscore.internal.fur
    - Highscore.internal.item
    - Highscore.internal.leather
    - Highscore.internal.meat
    - Highscore.internal.ore
    - Highscore.internal.skin

    Fields:
    - bought    (IntField)
    - obtained  (IntField)
    - recycled  (IntField)
    - sold      (IntField)
    """
    bought = IntField(required=True, default=0)
    obtained = IntField(required=True, default=0)
    recycled = IntField(required=True, default=0)
    sold = IntField(required=True, default=0)


class HighscoreInternalShardRarity(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal.shard.<rarity>

    Fields:
    - bought    (IntField)
    - obtained  (IntField)
    - recycled  (IntField)
    - sold      (IntField)
    - used      (IntField)
    """
    bought = IntField(required=True, default=0)
    obtained = IntField(required=True, default=0)
    recycled = IntField(required=True, default=0)
    sold = IntField(required=True, default=0)
    used = IntField(required=True, default=0)


class HighscoreInternalShard(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal.shard
    One sub-document per mongo.constants.RARITY, in lowercase like Satchel.shard

    Fields:
    - broken    (EmbeddedDocumentField)
    - common    (EmbeddedDocumentField)
    - uncommon  (EmbeddedDocumentField)
    - rare      (EmbeddedDocumentField)
    - epic      (EmbeddedDocumentField)
    - legendary (EmbeddedDocumentField)
    """
    broken = EmbeddedDocumentField(
        HighscoreInternalShardRarity, required=True, default=HighscoreInternalShardRarity)
    common = EmbeddedDocumentField(
        HighscoreInternalShardRarity, required=True, default=HighscoreInternalShardRarity)
    uncommon = EmbeddedDocumentField(
        HighscoreInternalShardRarity, required=True, default=HighscoreInternalShardRarity)
    rare = EmbeddedDocumentField(
        HighscoreInternalShardRarity, required=True, default=HighscoreInternalShardRarity)
    epic = EmbeddedDocumentField(
        HighscoreInternalShardRarity, required=True, default=HighscoreInternalShardRarity)
    legendary = EmbeddedDocumentField(
        HighscoreInternalShardRarity, required=True, default=HighscoreInternalShardRarity)


class HighscoreInternalConsumableCreated(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal.consumable.health.<kind>

    Fields:
    - created   (IntField)
    """
    created = IntField(required=True, default=0)


class HighscoreInternalConsumableHealth(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal.consumable.health
    Same kinds as Satchel.consumable.health

    Fields:
    - base      (EmbeddedDocumentField)
    - fast      (EmbeddedDocumentField)
    - long      (EmbeddedDocumentField)
    """
    base = EmbeddedDocumentField(
        HighscoreInternalConsumableCreated, required=True,
        default=HighscoreInternalConsumableCreated)
    fast = EmbeddedDocumentField(
        HighscoreInternalConsumableCreated, required=True,
        default=HighscoreInternalConsumableCreated)
    long = EmbeddedDocumentField(
        HighscoreInternalConsumableCreated, required=True,
        default=HighscoreInternalConsumableCreated)


class HighscoreInternalConsumable(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal.consumable

    Fields:
    - health    (EmbeddedDocumentField)
    """
    health = EmbeddedDocumentField(
        HighscoreInternalConsumableHealth, required=True,
        default=HighscoreInternalConsumableHealth)


class HighscoreInternalCurrency(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal.currency

    Fields:
    - spent     (IntField)
    """
    spent = IntField(required=True, default=0)


class HighscoreProfession(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.profession

    Fields:
    - gathering (IntField)
    - mining    (IntField)
    - mixology  (IntField)
    - recycling (IntField)
    - skinning  (IntField)
    - tanning   (IntField)
    - tracking  (IntField)
    """
    gathering = IntField(required=True, default=0)
    mining = IntField(required=True, default=0)
    mixology = IntField(required=True, default=0)
    recycling = IntField(required=True, default=0)
    skinning = IntField(required=True, default=0)
    tanning = IntField(required=True, default=0)
    tracking = IntField(required=True, default=0)


class HighscoreInternal(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.internal

    Fields:
    - consumable (EmbeddedDocumentField)
    - currency  (EmbeddedDocumentField)
    - fur       (EmbeddedDocumentField)
    - item      (EmbeddedDocumentField)
    - leather   (EmbeddedDocumentField)
    - meat      (EmbeddedDocumentField)
    - ore       (EmbeddedDocumentField)
    - shard     (EmbeddedDocumentField)
    - skin      (EmbeddedDocumentField)
    """
    # Documents created before these fields read them as zeros (defaults)
    consumable = EmbeddedDocumentField(
        HighscoreInternalConsumable, required=True, default=HighscoreInternalConsumable)
    currency = EmbeddedDocumentField(
        HighscoreInternalCurrency, required=True, default=HighscoreInternalCurrency)
    fur = EmbeddedDocumentField(HighscoreInternalGenericResource, required=True)
    item = EmbeddedDocumentField(HighscoreInternalGenericResource, required=True)
    leather = EmbeddedDocumentField(HighscoreInternalGenericResource, required=True)
    meat = EmbeddedDocumentField(HighscoreInternalGenericResource, required=True)
    ore = EmbeddedDocumentField(HighscoreInternalGenericResource, required=True)
    shard = EmbeddedDocumentField(
        HighscoreInternalShard, required=True, default=HighscoreInternalShard)
    skin = EmbeddedDocumentField(HighscoreInternalGenericResource, required=True)


class HighscoreGeneral(EmbeddedDocument):
    """
    Define the embedded document for: Highscore.general

    Fields:
    - assist (IntField)
    - death  (IntField)
    - kill   (IntField)
    """
    assist = IntField(required=True, default=0)
    death = IntField(required=True, default=0)
    kill = IntField(required=True, default=0)


class HighscoreDocument(Document):
    """
    Define the document for: Highscore

    Fields:
    - _id           (UUIDField)
    - created       (DateTimeField)
    - general       (EmbeddedDocumentField)
    - internal      (EmbeddedDocumentField)
    - profession    (EmbeddedDocumentField)
    - updated       (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True)
    created = DateTimeField(default=utcnow)
    general = EmbeddedDocumentField(HighscoreGeneral, required=True)
    internal = EmbeddedDocumentField(HighscoreInternal, required=True)
    profession = EmbeddedDocumentField(HighscoreProfession, required=True)
    updated = DateTimeField(default=utcnow)

    meta = {
        'collection': 'highscores',
        'indexes': [],
        'uuid_representation': 'standard'
        }
