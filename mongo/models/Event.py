# -*- coding: utf8 -*-

import datetime
import uuid

from mongoengine import (
    Document,
    )
from mongoengine.fields import (
    BooleanField,
    DateTimeField,
    DynamicField,
    # EmbeddedDocumentField,
    IntField,
    # DictField,
    # ListField,
    StringField,
    UUIDField,
)

#
# Collection: event
#


class EventDocument(Document):
    """
    Define the document for: Event

    Fields:
    - _id       (UUIDField)
    - action    (StringField)
    - created   (DateTimeField)
    - dst       (UUIDField)
    - extra     (DynamicField)
    - harmful   (BooleanField)
    - instance  (UUIDField)
    - name      (StringField)
    - src       (UUIDField)
    - trigger   (UUIDField)
    - type      (IntField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    action = StringField(required=True)
    created = DateTimeField(default=datetime.datetime.utcnow)
    dst = UUIDField(binary=False, default=None)
    extra = DynamicField()
    harmful = BooleanField(required=True, default=False)
    instance = UUIDField(binary=False, default=None)
    name = StringField(required=True)
    src = UUIDField(binary=False, default=None)
    trigger = UUIDField(binary=False, default=None)
    type = IntField(required=True)

    meta = {
        'collection': 'events',
        'indexes': [
            {'fields': ['created'], 'expireAfterSeconds': 2592000}  # ~= 1 month
        ],
        'uuid_representation': 'standard'
    }


"""
Comment about EventDocument.type:
Indices < 10 will be Fight Actions ones (reserved for Resolver)
Indices 10++ will be Generic Actions ones
"""
