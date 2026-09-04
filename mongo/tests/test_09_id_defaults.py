# -*- coding: utf8 -*-

import importlib
import os
import pkgutil
import sys

from mongoengine import Document

# Needed for local imports and simulate production paths
LOCAL_PATH = os.path.dirname(os.path.abspath('mongo'))
sys.path.append(LOCAL_PATH)

import mongo.models  # noqa: E402


def _models_with_auto_id():
    """Every Document subclass in mongo.models whose _id has a default -
    i.e. is meant to auto-generate a primary key when one isn't passed in.

    Historically several of these declared `default=uuid.uuid4()` (called
    once, at class-definition time) instead of `default=uuid.uuid4` (a
    factory mongoengine calls fresh per document) - every instance that
    didn't set its own _id then shared one UUID for the life of the
    process, silently overwriting the previous one on save(). See
    test_auto_id_default_generates_distinct_ids_per_instance below.
    """
    classes = []
    for _, modname, _ in pkgutil.iter_modules(mongo.models.__path__):
        module = importlib.import_module(f'mongo.models.{modname}')
        for name in dir(module):
            obj = getattr(module, name)
            if not (isinstance(obj, type) and issubclass(obj, Document) and obj is not Document):
                continue
            # Abstract base classes imported into a model's namespace (e.g.
            # DynamicDocument) aren't finalized the same way and don't
            # carry a real _fields mapping - skip anything without one.
            fields = getattr(obj, '_fields', None)
            if not fields:
                continue
            id_field = fields.get('_id')
            if id_field is not None and id_field.default is not None:
                classes.append(obj)
    return classes


def test_mongodb_id_defaults_are_discovered():
    # Sanity check on the discovery helper itself, so a refactor that
    # accidentally empties it doesn't make the real test below a silent
    # no-op.
    assert len(_models_with_auto_id()) >= 10


def test_mongodb_auto_id_default_generates_distinct_ids_per_instance():
    for cls in _models_with_auto_id():
        first = cls()
        second = cls()
        assert first.id != second.id, (
            f'{cls.__module__}.{cls.__name__} _id default produced the same '
            'value for two instances - likely default=X() (called once at '
            'class definition) instead of default=X (a factory mongoengine '
            'calls fresh per document).'
            )
