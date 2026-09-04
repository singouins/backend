# -*- coding: utf8 -*-

import datetime
import uuid

from mongoengine import (
    Document,
    )
from mongoengine.fields import (
    # BooleanField,
    DateTimeField,
    # DynamicField,
    # EmbeddedDocumentField,
    IntField,
    # DictField,
    # ListField,
    # StringField,
    UUIDField,
)

#
# Collection: aggro
#


class AggroDocument(Document):
    """
    Define the document for: Aggro

    Fields:
    - _id       (UUIDField)
    - amount    (IntField)
    - created   (DateTimeField)
    - bearer    (UUIDField)
    - instance  (UUIDField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    amount = IntField(default=0)
    bearer = UUIDField(binary=False, required=True, default=None)
    created = DateTimeField(default=datetime.datetime.utcnow)
    instance = UUIDField(binary=False, default=None)

    meta = {
        'collection': 'aggros',
        'indexes': [
            {'fields': ['created'], 'expireAfterSeconds': 2592000}  # ~= 1 month
        ],
        'uuid_representation': 'standard'
    }
