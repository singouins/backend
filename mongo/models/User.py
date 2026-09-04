import datetime
import uuid

from mongoengine import (
    Document,
    EmbeddedDocument,
    )
from mongoengine.fields import (
    BooleanField,
    DateTimeField,
    EmbeddedDocumentField,
    # IntField,
    # DictField,
    # ListField,
    StringField,
    UUIDField,
)

#
# Collection: user
#


class UserDiscord(EmbeddedDocument):
    """
    Define the embedded document for: User.discord

    Fields:
    - ack   (IntField)
    - name  (StringField)
    """
    ack = BooleanField(default=False)
    name = StringField(default=None)


class UserDocument(Document):
    """
    Define the document for: User

    Fields:
    - _id       (UUIDField)
    - active    (BooleanField)
    - created   (DateTimeField)
    - discord   (EmbeddedDocumentField)
    - hash      (StringField)
    - name      (StringField)
    - updated   (DateTimeField)
    """
    _id = UUIDField(binary=False, primary_key=True, default=uuid.uuid4)
    active = BooleanField(required=True, default=False)
    created = DateTimeField(default=datetime.datetime.utcnow)
    discord = EmbeddedDocumentField(UserDiscord, required=True)
    hash = StringField(required=True)
    name = StringField(required=True)
    updated = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        'collection': 'users',
        'indexes': [],
        'uuid_representation': 'standard'
        }
