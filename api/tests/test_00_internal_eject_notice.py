# -*- coding: utf8 -*-

import datetime
import os
import sys
import types
import uuid

import pytest
from flask import Flask

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

# Designer ruling (2026-10-10): a Singouin's death is announced on Discord by
# the internal eject route. When the reason is 'death' and the creature is
# actually ejected ('left' or 'closed'), one message is queued per scope:
# its Korp, then its Squad. Nothing is queued on 'gone', for another reason,
# or when the eject fails. Pure unit test: no Mongo, no Redis.

TOKEN = 'unit-test-token'
YQ_DISCORD = 'pytest:yarqueue:discord'
INSTANCE_ID = uuid.uuid4()
CREATURE_ID = uuid.uuid4()
KORP_ID = uuid.uuid4()
SQUAD_ID = uuid.uuid4()

# routes.internal.instance imports the Mongo models, directly and through
# utils.decorators / utils.instance. Importing the real mongo package connects
# to Mongo and loads the metas (mongo/__init__.py), so these leaves are stubbed
# in sys.modules: once a dotted name is there, Python never imports its parents.
MODEL_STUBS = {
    'mongo.models.Creature': ['CreatureDocument'],
    'mongo.models.Instance': ['InstanceDocument'],
    'mongo.models.Item': ['ItemDocument'],
    'mongo.models.Korp': ['KorpDocument'],
    'mongo.models.Squad': ['SquadDocument'],
    'mongo.models.User': ['UserDocument'],
    }
# Modules bound to the stubs at import: imported fresh here, then dropped
# (and any previous copy put back) so that no other test sees them
ISOLATED = [
    'routes.internal',
    'routes.internal.instance',
    'utils.decorators',
    'utils.instance',
    ]
# Marks a parent package attribute that did not exist before the import
_ABSENT = object()


class _Query:
    """ Stands for Document.objects(...): .first() returns the given document. """
    def __init__(self, document):
        self.document = document

    def __call__(self, **kwargs):
        return self

    def first(self):
        return self.document


def _creature(korp_id=None, squad_id=None, korp=True, squad=True):
    """
    A Singouin as the route reads it. Like the real CreatureKorp/CreatureSquad,
    the embedded documents exist with id None when there is no membership;
    korp/squad False means the embedded document itself is None (old docs).
    """
    return types.SimpleNamespace(
        id=CREATURE_ID,
        name='PJTest',
        account=uuid.uuid4(),
        instance=INSTANCE_ID,
        korp=types.SimpleNamespace(id=korp_id, rank=None) if korp else None,
        squad=types.SimpleNamespace(id=squad_id, rank=None) if squad else None,
        )


@pytest.fixture
def route(monkeypatch):
    """
    Imports routes.internal.instance against stubbed models. Inside api/tests,
    `variables` resolves to tests/variables.py (loaded by conftest), not
    api/variables.py (which connects to Mongo at import), so the names the
    imported modules need from it are provided here.
    """
    variables = sys.modules['variables']
    monkeypatch.setattr(variables, 'SEP_INTERNAL_TOKEN', TOKEN, raising=False)
    monkeypatch.setattr(variables, 'YQ_DISCORD', YQ_DISCORD, raising=False)
    # Same keys as api/variables.py: utils.redis builds its (lazy) pool from them at import
    monkeypatch.setattr(variables, 'env_vars', {
        'API_ENV': 'pytest',
        'REDIS_HOST': '127.0.0.1',
        'REDIS_PORT': 6379,
        'REDIS_BASE': 0,
        }, raising=False)

    for name, attributes in MODEL_STUBS.items():
        stub = types.ModuleType(name)
        for attribute in attributes:
            setattr(stub, attribute, None)
        monkeypatch.setitem(sys.modules, name, stub)

    # An import also binds the module on its parent package (utils.instance,
    # routes.internal, ...), and `from utils import instance` reads that
    # attribute: it is saved here and put back too
    saved = {}
    for name in ISOLATED:
        parent, _, child = name.rpartition('.')
        parent_module = sys.modules.get(parent)
        attribute = _ABSENT if parent_module is None else getattr(parent_module, child, _ABSENT)
        saved[name] = (sys.modules.pop(name, None), attribute)
    try:
        import routes.internal.instance as module
        yield module
    finally:
        for name, (previous, _) in saved.items():
            sys.modules.pop(name, None)
            if previous is not None:
                sys.modules[name] = previous
        for name, (_, attribute) in saved.items():
            parent, _, child = name.rpartition('.')
            parent_module = sys.modules.get(parent)
            if parent_module is None:
                continue
            if attribute is _ABSENT:
                if hasattr(parent_module, child):
                    delattr(parent_module, child)
            else:
                setattr(parent_module, child, attribute)


@pytest.fixture
def eject(route, monkeypatch):
    """
    Runs the eject view on a minimal Flask app, with the Creature/Instance
    lookups, leave_instance() and qput() replaced in the route module.
    Returns post(creature, result, reason) -> (response, queued messages).
    """
    queued = []
    monkeypatch.setattr(route, 'qput', lambda queue, msg: queued.append((queue, msg)))
    monkeypatch.setattr(route, 'purge_creature_keys', lambda **kwargs: None)

    app = Flask(__name__)
    app.add_url_rule(
        '/eject/<string:instanceid>/<string:creatureid>',
        methods=['POST'],
        view_func=route.eject,
        )
    client = app.test_client()

    def post(creature, result='left', reason='death', instance=True):
        monkeypatch.setattr(route, 'CreatureDocument', types.SimpleNamespace(objects=_Query(creature)))  # noqa: E501
        monkeypatch.setattr(route, 'InstanceDocument', types.SimpleNamespace(
            objects=_Query(types.SimpleNamespace(id=INSTANCE_ID) if instance else None)))
        if isinstance(result, Exception):
            def leave(Creature, Instance):
                raise result
        else:
            def leave(Creature, Instance):
                return result
        monkeypatch.setattr(route, 'leave_instance', leave)
        if instance is False and creature is not None:
            # Dangling path: the route detaches and saves the Creature itself
            creature.save = lambda: None

        queued.clear()
        response = client.post(
            f'/eject/{INSTANCE_ID}/{CREATURE_ID}',
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "reason": reason,
                "by": None,
                "at": datetime.datetime.utcnow().isoformat(),
                "requestId": str(uuid.uuid4()),
                },
            )
        return response, list(queued)

    return post


def _message(scope):
    return (YQ_DISCORD, {
        "ciphered": False,
        "payload": ':skull: **PJTest** died in an Instance',
        "embed": None,
        "scope": scope,
        })


#
# _death_scopes(), on each field alone
#
def test_death_scopes_korp_and_squad(route):
    scopes = route._death_scopes(_creature(korp_id=KORP_ID, squad_id=SQUAD_ID))
    assert scopes == [f'Korp-{KORP_ID}', f'Squad-{SQUAD_ID}']


def test_death_scopes_korp_only(route):
    assert route._death_scopes(_creature(korp_id=KORP_ID)) == [f'Korp-{KORP_ID}']


def test_death_scopes_squad_only(route):
    assert route._death_scopes(_creature(squad_id=SQUAD_ID)) == [f'Squad-{SQUAD_ID}']


def test_death_scopes_none_ids(route):
    # Embedded documents present, ids None: no membership
    assert route._death_scopes(_creature()) == []


def test_death_scopes_no_embedded_documents(route):
    assert route._death_scopes(_creature(korp=False, squad=False)) == []
    assert route._death_scopes(_creature(squad_id=SQUAD_ID, korp=False)) == [f'Squad-{SQUAD_ID}']  # noqa: E501
    assert route._death_scopes(_creature(korp_id=KORP_ID, squad=False)) == [f'Korp-{KORP_ID}']


#
# The route: what is queued, and when
#
@pytest.mark.parametrize('result', ['left', 'closed'])
def test_eject_death_korp_and_squad_queues_two(eject, result):
    response, queued = eject(_creature(korp_id=KORP_ID, squad_id=SQUAD_ID), result=result)
    assert response.status_code == 200
    assert response.json['payload'] == {"result": result}
    assert queued == [_message(f'Korp-{KORP_ID}'), _message(f'Squad-{SQUAD_ID}')]


def test_eject_death_squad_only_queues_one(eject):
    response, queued = eject(_creature(squad_id=SQUAD_ID))
    assert response.status_code == 200
    assert queued == [_message(f'Squad-{SQUAD_ID}')]


def test_eject_death_korp_only_queues_one(eject):
    response, queued = eject(_creature(korp_id=KORP_ID))
    assert response.status_code == 200
    assert queued == [_message(f'Korp-{KORP_ID}')]


def test_eject_death_no_korp_no_squad_queues_none(eject):
    response, queued = eject(_creature())
    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'left'}
    assert queued == []


def test_eject_death_second_call_gone_queues_none(eject):
    creature = _creature(korp_id=KORP_ID, squad_id=SQUAD_ID)
    response, queued = eject(creature)
    assert response.json['payload'] == {"result": 'left'}
    assert len(queued) == 2

    # The retry finds the Creature out of the instance: gone, nothing queued
    creature.instance = None
    response, queued = eject(creature)
    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'gone'}
    assert queued == []


def test_eject_unknown_creature_gone_queues_none(eject):
    response, queued = eject(None)
    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'gone'}
    assert queued == []


@pytest.mark.parametrize('reason', ['kick', 'Death', 'timeout'])
def test_eject_other_reason_queues_none(eject, reason):
    response, queued = eject(_creature(korp_id=KORP_ID, squad_id=SQUAD_ID), reason=reason)
    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'left'}
    assert queued == []


def test_eject_death_dangling_instance_queues(eject):
    # Instance NOTFOUND: the route detaches the Creature itself, result 'left'
    response, queued = eject(_creature(korp_id=KORP_ID, squad_id=SQUAD_ID), instance=False)
    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'left'}
    assert queued == [_message(f'Korp-{KORP_ID}'), _message(f'Squad-{SQUAD_ID}')]


def test_eject_death_failure_is_500_and_queues_none(eject):
    response, queued = eject(_creature(korp_id=KORP_ID, squad_id=SQUAD_ID), result=RuntimeError('boom'))  # noqa: E501
    assert response.status_code == 500
    assert response.json['success'] is False
    assert queued == []


def test_eject_death_monster_is_400_and_queues_none(eject):
    creature = _creature(korp_id=KORP_ID, squad_id=SQUAD_ID)
    creature.account = None
    response, queued = eject(creature)
    assert response.status_code == 400
    assert queued == []


def test_eject_death_announce_failure_keeps_the_200(eject, route, monkeypatch):
    def broken(queue, msg):
        raise RuntimeError('queue down')
    monkeypatch.setattr(route, 'qput', broken)

    response, _ = eject(_creature(korp_id=KORP_ID, squad_id=SQUAD_ID), result='closed')
    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'closed'}


#
# Isolation: runs last in this file, after every use of the route fixture
#
def test_isolation_leaves_no_stub_bound_module():
    for name in ISOLATED:
        parent, _, child = name.rpartition('.')
        current = sys.modules.get(name)
        assert getattr(current, 'CreatureDocument', 'real') is not None
        parent_module = sys.modules.get(parent)
        if parent_module is not None and hasattr(parent_module, child):
            # `from <parent> import <child>` must give what sys.modules holds
            assert getattr(parent_module, child) is current
