# -*- coding: utf8 -*-

import datetime
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
    # ListField,
    StringField,
    UUIDField,
)

CREATURE_RARITY = [
    'Small',
    'Medium',
    'Big',
    'Unique',
    'Boss',
    'God',
    ]

#
# Collection: corpse
#


class CorpseDocument(Document):
    """
    Define the document for: Corpse

    Fields:
    - _id       (UUIDField)
    - account   (UUIDField)
    - created   (DateTimeField)
    - gender    (BooleanField)
    - instance  (UUIDField)
    - killer    (UUIDField)
    - level     (IntField)
    - name      (StringField)
    - race      (IntField)
    - rarity    (StringField)
    - x         (IntField)
    - y         (IntField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    account = UUIDField(binary=False, default=None)
    created = DateTimeField(default=datetime.datetime.utcnow)
    gender = BooleanField(required=True)
    instance = UUIDField(binary=False, required=True)
    killer = UUIDField(binary=False)
    level = IntField(required=True, default=1)
    name = StringField(required=True)
    race = IntField(required=True)
    rarity = StringField(required=True, choices=CREATURE_RARITY, default='Medium')
    x = IntField(default=None)
    y = IntField(default=None)

    meta = {
        'collection': 'corpses',
        'indexes': [],
        'uuid_representation': 'standard'
    }
