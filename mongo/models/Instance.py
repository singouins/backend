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
    ListField,
    # StringField,
    UUIDField,
)

from mongo.utils import utcnow

#
# Collection: instance
#


class InstanceDocument(Document):
    """
    Define the document for: Instance

    Fields:
    - _id       (UUIDField)
    - created   (DateTimeField)
    - creator   (UUIDField)
    - fast      (BooleanField)
    - hardcore  (BooleanField)
    - leavers   (ListField)
    - map       (IntField)
    - public    (BooleanField)
    - tick      (IntField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    created = DateTimeField(default=utcnow)
    creator = UUIDField(binary=False, required=True)
    fast = BooleanField(required=True, default=False)
    hardcore = BooleanField(required=True, default=False)
    # Creatures (uuids) that left this instance and may not re-enter it
    leavers = ListField(UUIDField(binary=False), default=list)
    map = IntField(required=True)
    public = BooleanField(required=True, default=True)
    tick = IntField(required=True, default=3600)
    updated = DateTimeField(default=utcnow)

    meta = {
        'collection': 'instances',
        'indexes': [],
        'uuid_representation': 'standard'
    }
