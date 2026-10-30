# -*- coding: utf8 -*-

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

from mongo.constants import RARITY
from mongo.utils import utcnow

#
# Collection: auction
#


class AuctionItem(EmbeddedDocument):
    """
    Define the embedded document for: Auction.item

    Fields:
    - id        (UUIDField)
    - metaid    (IntField)
    - metatype  (StringField)
    - name      (StringField)
    - rarity    (StringField)
    """
    id = UUIDField(binary=False, default=None)
    metaid = IntField(required=True)
    metatype = StringField(required=True)
    name = StringField(required=True)
    rarity = StringField(required=True, choices=RARITY)


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
    - item      (EmbeddedDocumentField)
    - price     (IntField)
    - seller    (EmbeddedDocumentField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    created = DateTimeField(default=utcnow)
    item = EmbeddedDocumentField(AuctionItem, required=True)
    price = IntField(required=True)
    seller = EmbeddedDocumentField(AuctionSeller, required=True)
    updated = DateTimeField(default=utcnow)

    meta = {
        'collection': 'auctions',
        'indexes': [
            {'fields': ['created'], 'expireAfterSeconds': 172800}  # == 48 hours
        ],
        'uuid_representation': 'standard'
    }
