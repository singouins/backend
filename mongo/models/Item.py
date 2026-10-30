# -*- coding: utf8 -*-

import uuid

from mongoengine import (
    Document,
    # EmbeddedDocument,
    )
from mongoengine.fields import (
    BooleanField,
    DateTimeField,
    # EmbeddedDocumentField,
    IntField,
    # DictField,
    ListField,
    StringField,
    UUIDField,
)

from mongo.utils import utcnow

ITEM_RARITY = [
    'Broken',
    'Common',
    'Uncommon',
    'Rare',
    'Epic',
    'Legendary',
    ]

#
# Collection: item
#


class ItemDocument(Document):
    """
    Define the document for: Item

    Fields:
    - _id         (UUIDField)
    - ammo        (IntField)
    - auctioned   (BooleanField)
    - bearer      (UUIDField)
    - bound       (BooleanField)
    - bound_type  (StringField)
    - created     (DateTimeField)
    - locked      (DateTimeField)
    - metaid      (IntField)
    - metatype    (StringField)
    - modded      (BooleanField)
    - mods        (ListField)
    - offsetx     (IntField)
    - offsety     (IntField)
    - rarity      (StringField)
    - state       (IntField)
    - updated     (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    ammo = IntField(default=None)
    auctioned = BooleanField(required=True, default=False)
    bearer = UUIDField(required=True, binary=False)
    bound = BooleanField(required=True, default=True)
    bound_type = StringField(required=True, default='BoP')
    created = DateTimeField(default=utcnow)
    # Set while an equip or a recycling holds the Item (api/utils/item_lock.py)
    locked = DateTimeField(default=None)
    metatype = StringField(required=True)
    metaid = IntField(required=True)
    modded = BooleanField(required=True, default=False)
    mods = ListField(default=list)
    offsetx = IntField(default=None)
    offsety = IntField(default=None)
    rarity = StringField(required=True, choices=ITEM_RARITY, default='Common')
    state = IntField(required=True, default=100)
    updated = DateTimeField(default=utcnow)

    meta = {
        'collection': 'items',
        'indexes': [],
        'uuid_representation': 'standard'
    }
