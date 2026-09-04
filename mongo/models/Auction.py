# -*- coding: utf8 -*-

import datetime
import uuid

from mongoengine import (
    Document,
    EmbeddedDocument,
    )
from mongoengine.fields import (
    # BooleanField,
    DateTimeField,
    EmbeddedDocumentField,
    IntField,
    # DictField,
    # ListField,
    # ReferenceField,
    StringField,
    UUIDField,
)

ITEM_RARITY = [
    'Broken',
    'Common',
    'Uncommon',
    'Rare',
    'Epic',
    'Legendary',
    ]

#
# Collection: auction
#


class AuctionItem(EmbeddedDocument):
    """
    Define the embedded document for: Auction.item

    Fields:
    - id        (UUIDField)
    - metaid    (UUIDField)
    - metatype  (StringField)
    - rarity    (StringField)
    """
    id = UUIDField(binary=False, default=None)
    metaid = IntField(required=True)
    metatype = StringField(required=True)
    name = StringField(required=True)
    rarity = StringField(required=True, choices=ITEM_RARITY)


class AuctionSeller(EmbeddedDocument):
    """
    Define the embedded document for: Auction.seller

    Fields:
    - id        (UUIDField)
    - name      (StringField)
    """
    id = UUIDField(binary=False, default=None)
    name = StringField(required=True)


class AuctionDocument(Document):
    """
    Define the document for: Auction

    Fields:
    - _id       (UUIDField)
    - created   (DateTimeField)
    - item      (UUIDField)
    - price     (IntField)
    - seller    (UUIDField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    created = DateTimeField(default=datetime.datetime.utcnow)
    item = EmbeddedDocumentField(AuctionItem, required=True)
    price = IntField(required=True)
    seller = EmbeddedDocumentField(AuctionSeller, required=True)
    updated = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        'collection': 'auctions',
        'indexes': [
            {'fields': ['created'], 'expireAfterSeconds': 172800}  # == 48 hours
        ],
        'uuid_representation': 'standard'
    }
