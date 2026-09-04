import datetime
import uuid

from mongoengine import (
    Document,
    # EmbeddedDocument,
    )
from mongoengine.fields import (
    DateTimeField,
    # EmbeddedDocumentField,
    # IntField,
    # DictField,
    # ListField,
    StringField,
    UUIDField,
)

#
# Collection: korp
#


class KorpDocument(Document):
    """
    Define the document for: Korp

    Fields:
    - _id       (UUIDField)
    - created   (DateTimeField)
    - leader    (UUIDField)
    - name      (StringField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    created = DateTimeField(default=datetime.datetime.utcnow)
    leader = UUIDField(required=True)
    name = StringField(binary=False, required=True)
    updated = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        'collection': 'korps',
        'indexes': [],
        'uuid_representation': 'standard'
    }
