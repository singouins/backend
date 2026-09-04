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
    # StringField,
    UUIDField,
)

#
# Collection: squad
#


class SquadDocument(Document):
    """
    Define the document for: Squad

    Fields:
    - _id       (UUIDField)
    - created   (DateTimeField)
    - leader    (UUIDField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    created = DateTimeField(default=datetime.datetime.utcnow)
    leader = UUIDField(binary=False, required=True)
    updated = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        'collection': 'squads',
        'indexes': [],
        'uuid_representation': 'standard'
    }
