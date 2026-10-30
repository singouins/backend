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

from mongo.utils import utcnow

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
    created = DateTimeField(default=utcnow)
    leader = UUIDField(binary=False, required=True)
    name = StringField(required=True)
    updated = DateTimeField(default=utcnow)

    meta = {
        'collection': 'korps',
        'indexes': [],
        'uuid_representation': 'standard'
    }
