# -*- coding: utf8 -*-

import datetime
import importlib.util
import os
import sys
import types
import uuid

import mongoengine
import mongomock
import pytest

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# Lordslair 2026-10-29: two recyclings of one Item credit its shards once, and
# an equip racing a recycling of the same Item never ends with a recycled
# Item equipped. Both routes lock the Item with one conditional update
# (utils/item_lock.py): this proves that only one caller gets the lock.
# Unit test: no Redis, the Items are real documents on an in-memory
# mongomock, so the conditional updates run for real.
REPO_PATH = os.path.join(LOCAL_PATH, os.pardir)
ITEM_MODEL = os.path.join(REPO_PATH, 'mongo', 'models', 'Item.py')
MONGO_UTILS = os.path.join(REPO_PATH, 'mongo', 'utils.py')
MONGO_CONSTANTS = os.path.join(REPO_PATH, 'mongo', 'constants.py')
ITEM_LOCK = os.path.join(LOCAL_PATH, 'utils', 'item_lock.py')
MOCK_ALIAS = 'test-item-lock'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mongo():
    """
    In-memory Mongo on its own alias, dropped after the test: in CI the
    default alias may already point at the real Mongo, registered by another
    test importing the mongo package.
    """
    mongoengine.connect(
        'pytest', alias=MOCK_ALIAS, mongo_client_class=mongomock.MongoClient,
        uuidRepresentation='standard',
        )
    yield
    # mongomock keeps its data while any client lives: drop it explicitly
    mongoengine.connection.get_connection(MOCK_ALIAS).drop_database('pytest')
    mongoengine.disconnect(alias=MOCK_ALIAS)


@pytest.fixture
def lock(mongo, monkeypatch):
    """
    Loads utils/item_lock.py with the real Item model. Item.py imports
    mongo.utils/constants: the real files are given under a stub mongo package, so
    mongo/__init__.py (and its connect()) never runs.
    """
    package = types.ModuleType('mongo')
    package.__path__ = []
    monkeypatch.setitem(sys.modules, 'mongo', package)
    monkeypatch.setitem(sys.modules, 'mongo.utils', _load('mongo.utils', MONGO_UTILS))
    monkeypatch.setitem(sys.modules, 'mongo.constants', _load('mongo.constants', MONGO_CONSTANTS))
    item_model = _load('test_item_lock_model', ITEM_MODEL)
    item_model.ItemDocument._meta['db_alias'] = MOCK_ALIAS
    monkeypatch.setitem(sys.modules, 'mongo.models.Item', item_model)
    module = _load('test_item_lock', ITEM_LOCK)

    def item(**fields):
        return item_model.ItemDocument(
            bearer=uuid.uuid4(), metatype='weapon', metaid=11, **fields,
            ).save()

    def locked(document):
        return item_model.ItemDocument.objects(_id=document.id).get().locked

    return types.SimpleNamespace(
        lock_item=module.lock_item,
        unlock_item=module.unlock_item,
        delete_locked_item=module.delete_locked_item,
        ttl=module.ITEM_LOCK_TTL,
        item=item,
        locked=locked,
        model=item_model.ItemDocument,
        )


def test_a_free_item_is_locked(lock):
    item = lock.item()

    token = lock.lock_item(item.id)

    # The token is the lock date as Mongo stores it (to the millisecond)
    assert token is not None
    assert lock.locked(item) == token


def test_a_locked_item_is_refused_to_the_second_caller(lock):
    # Two recyclings, or an equip and a recycling: only the first gets it
    item = lock.item()

    assert lock.lock_item(item.id) is not None
    assert lock.lock_item(item.id) is None


def test_an_unlocked_item_can_be_locked_again(lock):
    # An equip releases it: the Item can be recycled later (or equipped again)
    item = lock.item()
    token = lock.lock_item(item.id)

    lock.unlock_item(item.id, token)

    assert lock.locked(item) is None
    assert lock.lock_item(item.id) is not None


def test_the_holder_deletes_the_item(lock):
    item = lock.item()
    token = lock.lock_item(item.id)

    assert lock.delete_locked_item(item.id, token) is True
    assert lock.model.objects(_id=item.id).count() == 0


def test_a_deleted_item_cannot_be_locked(lock):
    # An equip that comes after a recycling deleted the Item is refused
    item = lock.item()
    lock.delete_locked_item(item.id, lock.lock_item(item.id))

    assert lock.lock_item(item.id) is None


def test_an_expired_lock_is_taken_over(lock):
    # Only for a holder that crashed before releasing it
    stale = datetime.datetime(2026, 1, 1)
    item = lock.item(locked=stale)

    assert lock.lock_item(item.id) is not None
    assert lock.locked(item) > stale


def test_a_lock_younger_than_its_ttl_is_kept(lock):
    from mongo.utils import utcnow
    item = lock.item(locked=utcnow() - lock.ttl / 2)

    assert lock.lock_item(item.id) is None


def test_a_stalled_holder_cannot_act_under_the_next_lock(lock):
    # A holder stalled past the expiry: the next holder took the lock over.
    # The stalled one can neither delete the Item nor release that lock
    stale = datetime.datetime(2026, 1, 1)
    item = lock.item(locked=stale)
    token = lock.lock_item(item.id)

    assert lock.delete_locked_item(item.id, stale) is False
    lock.unlock_item(item.id, stale)

    assert lock.model.objects(_id=item.id).count() == 1
    assert lock.locked(item) == token


def test_unlocking_a_deleted_item_does_nothing(lock):
    item = lock.item()
    token = lock.lock_item(item.id)
    lock.delete_locked_item(item.id, token)

    lock.unlock_item(item.id, token)

    assert lock.model.objects(_id=item.id).count() == 0
