# -*- coding: utf8 -*-

import uuid

from mongoengine import (
    Document,
    EmbeddedDocument,
    )
from mongoengine.fields import (
    BooleanField,
    DateTimeField,
    EmbeddedDocumentField,
    IntField,
    # DictField,
    # ListField,
    StringField,
    UUIDField,
)

from mongo.constants import ITEM_BIND, RARITY
from mongo.utils import utcnow

#
# Collection: cosmetic
#


class CosmeticData(EmbeddedDocument):
    """
    Define the embedded document for: Cosmetic.data

    Fields:
    - beforeArmor   (BooleanField)
    - hasGender     (BooleanField)
    - hideArmor     (BooleanField)
    """
    beforeArmor = BooleanField(required=True, default=False)
    hasGender = BooleanField(required=True, default=True)
    hideArmor = BooleanField(required=True, default=False)


class CosmeticDocument(Document):
    """
    Define the document for: Cosmetic

    Fields:
    - _id         (UUIDField)
    - bearer      (UUIDField)
    - bound       (BooleanField)
    - bound_type  (StringField)
    - created     (DateTimeField)
    - data        (EmbeddedDocumentField)
    - metaid      (IntField)
    - rarity      (StringField)
    - state       (IntField)
    - updated     (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    bearer = UUIDField(required=True, binary=False)
    bound = BooleanField(required=True, default=True)
    bound_type = StringField(required=True, choices=ITEM_BIND, default='BoP')
    created = DateTimeField(default=utcnow)
    data = EmbeddedDocumentField(CosmeticData, required=True)
    metaid = IntField(required=True)
    rarity = StringField(required=True, choices=RARITY, default='Common')
    state = IntField(required=True, default=100)
    updated = DateTimeField(default=utcnow)

    meta = {
        'collection': 'cosmetics',
        'indexes': [],
        'uuid_representation': 'standard'
    }
