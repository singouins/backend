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
    # StringField,
    UUIDField,
)

#
# Collection: satchel
#


class SatchelResource(EmbeddedDocument):
    """
    Define the embedded document for: Satchel.resource

    Fields:
    - fur       (IntField)
    - leather   (IntField)
    - meat      (IntField)
    - ore       (IntField)
    - skin      (IntField)
    """
    fur = IntField(required=True, default=0)
    leather = IntField(required=True, default=0)
    meat = IntField(required=True, default=0)
    ore = IntField(required=True, default=0)
    skin = IntField(required=True, default=0)


class SatchelShard(EmbeddedDocument):
    """
    Define the embedded document for: Satchel.resource

    Fields:
    - broken    (IntField)
    - common    (IntField)
    - uncommon  (IntField)
    - rare      (IntField)
    - epic      (IntField)
    - legendary (IntField)
    """
    broken = IntField(required=True, default=0)
    common = IntField(required=True, default=0)
    uncommon = IntField(required=True, default=0)
    rare = IntField(required=True, default=0)
    epic = IntField(required=True, default=0)
    legendary = IntField(required=True, default=0)


class SatchelAmmo(EmbeddedDocument):
    """
    Define the embedded document for: Satchel.slots

    Fields:
    - arrow     (IntField)
    - bolt      (IntField)
    - cal22     (IntField)
    - cal223    (IntField)
    - cal311    (IntField)
    - cal50     (IntField)
    - cal55     (IntField)
    - fuel      (IntField)
    - grenade   (IntField)
    - rocket    (IntField)
    - shell     (IntField)
    """
    arrow = IntField(required=True, default=0)
    bolt = IntField(required=True, default=0)
    cal22 = IntField(required=True, default=0)
    cal223 = IntField(required=True, default=0)
    cal311 = IntField(required=True, default=0)
    cal50 = IntField(required=True, default=0)
    cal55 = IntField(required=True, default=0)
    fuel = IntField(required=True, default=0)
    grenade = IntField(required=True, default=0)
    rocket = IntField(required=True, default=0)
    shell = IntField(required=True, default=0)


class SatchelCurrency(EmbeddedDocument):
    """
    Define the embedded document for: Satchel.currency

    Fields:
    - banana    (IntField)
    - sausage   (IntField)
    """
    banana = IntField(required=True, default=0)
    sausage = IntField(required=True, default=0)


class SatchelDocument(Document):
    """
    Define the document for: Satchel

    Fields:
    - _id       (UUIDField)
    - ammo      (EmbeddedDocumentField)
    - currency  (EmbeddedDocumentField)
    - resource  (EmbeddedDocumentField)
    - shard     (EmbeddedDocumentField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    ammo = EmbeddedDocumentField(SatchelAmmo, required=True)
    currency = EmbeddedDocumentField(SatchelCurrency, required=True)
    resource = EmbeddedDocumentField(SatchelResource, required=True)
    shard = EmbeddedDocumentField(SatchelShard, required=True)
    updated = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        'collection': 'satchels',
        'indexes': [],
        'uuid_representation': 'standard'
    }
