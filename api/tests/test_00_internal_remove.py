# -*- coding: utf8 -*-

import importlib.util
import datetime
import json
import os
import sys
import types
import uuid

import mongoengine
import mongomock
import pytest
from flask import Flask

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)
CORPSE_MODEL = os.path.join(LOCAL_PATH, os.pardir, 'mongo', 'models', 'Corpse.py')
MONGO_UTILS = os.path.join(LOCAL_PATH, os.pardir, 'mongo', 'utils.py')
MONGO_CONSTANTS = os.path.join(LOCAL_PATH, os.pardir, 'mongo', 'constants.py')
MOCK_ALIAS = 'test-internal-remove'

# Designer ruling Q99 (2026-10-10): a dead monster is removed from the map at
# once. The fight resolver calls POST /internal/instance/<i>/creature/<c>/remove,
# which removes the monster as an instance close does (AI kill on the env
# channel, Redis keys purged, Creature deleted last). The AI listens on
# ai-creature-<env>, so every kill, the instance-close one too, goes there.
# Pure unit test: no Mongo, no Redis.

TOKEN = 'unit-test-token'
PS_AI_CREATURE = 'ai-creature-pytest'
INSTANCE_ID = uuid.uuid4()
OTHER_INSTANCE_ID = uuid.uuid4()
MONSTER_ID = uuid.uuid4()
SINGOUIN_ID = uuid.uuid4()

# Same stubbing as test_00_internal_eject_notice.py: routes.internal.instance
# imports the Mongo models (directly and through utils.decorators /
# utils.instance), and the real mongo package connects at import
MODEL_STUBS = {
    'mongo.models.Corpse': ['CorpseDocument'],
    'mongo.models.Creature': ['CreatureDocument'],
    'mongo.models.Highscore': ['HighscoreDocument'],
    'mongo.models.Instance': ['InstanceDocument'],
    'mongo.models.Item': ['ItemDocument'],
    'mongo.models.Korp': ['KorpDocument'],
    'mongo.models.Squad': ['SquadDocument'],
    'mongo.models.User': ['UserDocument'],
    }
ISOLATED = [
    'routes.internal',
    'routes.internal.instance',
    'routes.internal.instance._tools',
    'routes.internal.instance.eject',
    'routes.internal.instance.remove',
    'utils.decorators',
    'utils.instance',
    ]
_ABSENT = object()


@pytest.fixture
def modules(monkeypatch):
    """
    Imports routes.internal.instance.remove and utils.instance against stubbed models,
    then drops them (and puts any previous copy back). Inside api/tests,
    `variables` is tests/variables.py, so the names read at import are set there.
    """
    variables = sys.modules['variables']
    monkeypatch.setattr(variables, 'SEP_INTERNAL_TOKEN', TOKEN, raising=False)
    monkeypatch.setattr(variables, 'YQ_DISCORD', 'pytest:yarqueue:discord', raising=False)
    monkeypatch.setattr(variables, 'PS_AI_CREATURE', PS_AI_CREATURE, raising=False)
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

    saved = {}
    for name in ISOLATED:
        parent, _, child = name.rpartition('.')
        parent_module = sys.modules.get(parent)
        attribute = _ABSENT if parent_module is None else getattr(parent_module, child, _ABSENT)
        saved[name] = (sys.modules.pop(name, None), attribute)
    try:
        # Not `import ... as`: the package re-exports the remove() function under
        # the submodule's name, and that attribute would win over the module
        route = importlib.import_module('routes.internal.instance.remove')
        import utils.instance as utils_instance
        yield types.SimpleNamespace(route=route, utils_instance=utils_instance)
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
def corpse_model(monkeypatch):
    """
    The real Corpse model, loaded straight from its file (the mongo package
    connects at import) on an in-memory mongomock, so its save() and queryset
    delete() run for real. Dropped after the test.
    Its mongo.utils/constants imports get the real files under a stub
    mongo package, so mongo/__init__.py (and its connect()) never runs.
    The mock has its own alias: in CI the default one may already point at
    the real Mongo, registered by another test importing the mongo package.
    """
    package = types.ModuleType('mongo')
    package.__path__ = []
    monkeypatch.setitem(sys.modules, 'mongo', package)
    utils_spec = importlib.util.spec_from_file_location('mongo.utils', MONGO_UTILS)
    utils = importlib.util.module_from_spec(utils_spec)
    utils_spec.loader.exec_module(utils)
    monkeypatch.setitem(sys.modules, 'mongo.utils', utils)
    constants_spec = importlib.util.spec_from_file_location('mongo.constants', MONGO_CONSTANTS)
    constants = importlib.util.module_from_spec(constants_spec)
    constants_spec.loader.exec_module(constants)
    monkeypatch.setitem(sys.modules, 'mongo.constants', constants)
    spec = importlib.util.spec_from_file_location('test_internal_remove_corpse', CORPSE_MODEL)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    model.CorpseDocument._meta['db_alias'] = MOCK_ALIAS
    mongoengine.connect(
        'pytest', alias=MOCK_ALIAS, mongo_client_class=mongomock.MongoClient,
        uuidRepresentation='standard',
        )
    yield model
    # mongomock keeps its data while any client lives: drop it explicitly
    mongoengine.connection.get_connection(MOCK_ALIAS).drop_database('pytest')
    mongoengine.disconnect(alias=MOCK_ALIAS)


class _QuerySet:
    """ Stands for a filtered mongoengine QuerySet: iterable, only() is a no-op. """
    def __init__(self, documents):
        self.documents = documents

    def __iter__(self):
        return iter(self.documents)

    def only(self, *fields):
        return self


class _One:
    """
    Stands for Document.objects(_id=x, **filters): first(), only() (no-op) and
    update_one(set__level=, set__xp=), applied only if the document still
    matches the filters (returns 1, else 0). failures['xp'] makes it raise,
    failures['xp_for'] (an id) only for that document. Each callable in
    hooks['before_write'] runs once, just before a write (one per write): another
    kill landing between the route's read and its write.
    """
    def __init__(self, documents, _id, filters, failures, hooks):
        self.documents = documents
        self._id = _id
        self.filters = filters
        self.failures = failures
        self.hooks = hooks

    def first(self):
        return self.documents.get(self._id)

    def only(self, *fields):
        return self

    def update_one(self, set__level, set__xp):
        if self.failures.get('xp') is not None:
            raise self.failures['xp']
        if self.failures.get('xp_for') == self._id:
            raise RuntimeError('mongo down for this one')
        if self.hooks.get('before_write'):
            self.hooks['before_write'].pop(0)()
        document = self.documents.get(self._id)
        if document is None or any(getattr(document, k) != v for k, v in self.filters.items()):
            return 0
        document.level, document.xp = set__level, set__xp
        return 1


class _Highscores:
    """
    Stands for HighscoreDocument.objects: objects(_id=x).update_one() and
    objects(_id__in=[...]).update() $inc general.kill / general.assist in
    `counters` ({id: {'kill': n, 'assist': n}}, Singouins only), and return
    how many documents matched. failures['kill'] / failures['assist'] raise.
    """
    def __init__(self, counters, failures):
        self.counters = counters
        self.failures = failures

    def __call__(self, _id=None, _id__in=None):
        ids = [_id] if _id__in is None else _id__in
        matched = [self.counters[i] for i in ids if i in self.counters]

        def inc(counter):
            if self.failures.get(counter) is not None:
                raise self.failures[counter]
            for document in matched:
                document[counter] += 1
            return len(matched)

        return types.SimpleNamespace(
            update_one=lambda inc__general__kill, set__updated: inc('kill'),
            update=lambda inc__general__assist, set__updated: inc('assist'),
            )


class _Collection:
    """
    Stands for Document.objects: objects(_id=x, ...) is a _One;
    objects(_id__in=[...], account__ne=None) filters the dict into a _QuerySet.
    """
    def __init__(self, documents, failures=None, hooks=None):
        self.documents = documents
        self.failures = {} if failures is None else failures
        self.hooks = {} if hooks is None else hooks

    def __call__(self, _id=None, _id__in=None, account__ne=_ABSENT, **filters):
        if _id__in is None:
            return _One(self.documents, _id, filters, self.failures, self.hooks)
        return _QuerySet([
            document for key, document in self.documents.items()
            if key in _id__in and (account__ne is _ABSENT or document.account != account__ne)
            ])


def _document(events, store, _id, instance, account=None, delete_error=None,
              level=3, xp=0, rarity='Big'):
    """ A Creature: delete() records the call and drops it from the store. """
    def delete():
        if delete_error is not None:
            raise delete_error
        events.append(('delete', _id))
        store.pop(_id, None)
    return types.SimpleNamespace(
        id=_id,
        account=account,
        gender=True,
        instance=instance,
        level=level,
        name='Monster',
        race=11,
        rarity=rarity,
        x=4,
        xp=xp,
        y=5,
        to_json=lambda json_options=None: json.dumps({"_id": str(_id), "name": 'Monster'}),
        delete=delete,
        )


@pytest.fixture
def world(modules, corpse_model, monkeypatch):
    """
    Runs the remove view on a minimal Flask app. Creatures and Instances live
    in dicts; r.publish(), purge_creature_keys() and Creature.delete() append
    to `events` in call order. failures['publish'] / failures['purge'] set to
    an exception make that call raise instead (failures['xp'] for the XP
    update, see _One, with hooks; failures['kill'] / ['assist'] for the
    highscores, see _Highscores). Every Singouin added gets its highscore
    counters in `highscores`. Corpses are real documents on mongomock, read
    back with corpses().
    """
    route = modules.route
    monkeypatch.setattr(route, 'CorpseDocument', corpse_model.CorpseDocument)
    events = []
    creatures = {}
    failures = {}
    hooks = {}
    highscores = {}
    instances = {
        INSTANCE_ID: types.SimpleNamespace(
            id=INSTANCE_ID,
            to_json=lambda json_options=None: json.dumps({"_id": str(INSTANCE_ID)}),
            ),
        }
    monkeypatch.setattr(route, 'CreatureDocument', types.SimpleNamespace(objects=_Collection(creatures, failures, hooks)))  # noqa: E501
    monkeypatch.setattr(route, 'InstanceDocument', types.SimpleNamespace(objects=_Collection(instances)))  # noqa: E501
    monkeypatch.setattr(route, 'HighscoreDocument', types.SimpleNamespace(objects=_Highscores(highscores, failures)))  # noqa: E501

    def publish(channel, data):
        if failures.get('publish') is not None:
            raise failures['publish']
        events.append(('publish', channel, json.loads(data)))

    def purge(**kwargs):
        if failures.get('purge') is not None:
            raise failures['purge']
        events.append(('purge', kwargs))

    monkeypatch.setattr(route, 'r', types.SimpleNamespace(publish=publish))
    monkeypatch.setattr(route, 'purge_creature_keys', purge)

    app = Flask(__name__)
    app.add_url_rule(
        '/remove/<string:instanceid>/<string:creatureid>',
        methods=['POST'],
        view_func=route.remove,
        )
    client = app.test_client()

    def add(_id, instance=INSTANCE_ID, account=None, delete_error=None, **fields):
        creatures[_id] = _document(
            events, creatures, _id, instance, account, delete_error, **fields)
        if account is not None:
            highscores.setdefault(_id, {'kill': 0, 'assist': 0})
        return creatures[_id]

    def post(creatureid=MONSTER_ID, instanceid=INSTANCE_ID, body=None, token=TOKEN):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if body is None:
            body = {
                "reason": 'death',
                "by": str(uuid.uuid4()),
                "at": datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat(),
                "requestId": str(uuid.uuid4()),
                }
        return client.post(f'/remove/{instanceid}/{creatureid}', headers=headers, json=body)

    def corpses():
        return list(corpse_model.CorpseDocument.objects())

    return types.SimpleNamespace(
        add=add, post=post, events=events, creatures=creatures, instances=instances,
        failures=failures, hooks=hooks, corpses=corpses, route=route,
        highscores=highscores,
        )


#
# The route
#
def test_remove_monster_is_removed(world):
    world.add(MONSTER_ID)

    response = world.post()

    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'removed'}
    assert world.events == [
        ('publish', PS_AI_CREATURE, {
            "action": 'kill',
            "instance": json.dumps({"_id": str(INSTANCE_ID)}),
            "creature": json.dumps({"_id": str(MONSTER_ID), "name": 'Monster'}),
            }),
        ('purge', {"creatureuuid": MONSTER_ID, "instanceuuid": INSTANCE_ID}),
        ('delete', MONSTER_ID),
        ]
    assert MONSTER_ID not in world.creatures


def test_remove_retry_after_removed_is_gone(world):
    world.add(MONSTER_ID)
    assert world.post().json['payload'] == {"result": 'removed'}
    world.events.clear()

    response = world.post()

    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'gone'}
    assert world.events == []


def test_remove_unknown_creature_is_gone(world):
    response = world.post()

    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['payload'] == {"result": 'gone'}
    assert world.events == []


@pytest.mark.parametrize('instance', [OTHER_INSTANCE_ID, None])
def test_remove_creature_in_another_instance_is_gone(world, instance):
    world.add(MONSTER_ID, instance=instance)

    response = world.post()

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'gone'}
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_unknown_instance_is_404(world):
    world.add(MONSTER_ID, instance=OTHER_INSTANCE_ID)

    response = world.post(instanceid=OTHER_INSTANCE_ID)

    assert response.status_code == 404
    assert response.json['success'] is False
    assert response.json['payload'] is None
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_singouin_is_400_and_touches_nothing(world):
    world.add(SINGOUIN_ID, account=uuid.uuid4())

    response = world.post(creatureid=SINGOUIN_ID)

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []
    assert SINGOUIN_ID in world.creatures


@pytest.mark.parametrize('instanceid, creatureid', [
    ('not-a-uuid', MONSTER_ID),
    (INSTANCE_ID, 'not-a-uuid'),
    ])
def test_remove_malformed_id_is_400(world, instanceid, creatureid):
    world.add(MONSTER_ID)

    response = world.post(creatureid=creatureid, instanceid=instanceid)

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []


@pytest.mark.parametrize('body', [
    [],
    {"reason": 'death', "at": '2026-10-10T00:00:00'},  # requestId missing
    {"reason": 'death', "at": 'yesterday', "requestId": str(uuid.uuid4())},
    ])
def test_remove_invalid_body_is_400(world, body):
    world.add(MONSTER_ID)

    response = world.post(body=body)

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_delete_failure_is_500(world):
    world.add(MONSTER_ID, delete_error=RuntimeError('mongo down'))

    response = world.post()

    assert response.status_code == 500
    assert response.json['success'] is False
    assert response.json['payload'] is None


def test_remove_without_token_is_401(world):
    world.add(MONSTER_ID)

    response = world.post(token=None)

    assert response.status_code == 401
    assert world.events == []
    assert MONSTER_ID in world.creatures


def _kill(creature_json):
    return ('publish', PS_AI_CREATURE, {
        "action": 'kill',
        "instance": json.dumps({"_id": str(INSTANCE_ID)}),
        "creature": creature_json,
        })


#
# Precedence between the answers: token, then 400, then 404, then gone
#
@pytest.mark.parametrize('instance', [None, OTHER_INSTANCE_ID])
def test_remove_unknown_instance_wins_over_gone(world, instance):
    # Unknown Instance AND a creature that would be 'gone' (unknown, or elsewhere)
    unknown = uuid.uuid4()
    if instance is not None:
        world.add(MONSTER_ID, instance=instance)

    response = world.post(
        creatureid=MONSTER_ID if instance is not None else uuid.uuid4(),
        instanceid=unknown,
        )

    assert response.status_code == 404
    assert response.json['success'] is False
    assert world.events == []


def test_remove_invalid_body_wins_over_unknown_instance(world):
    response = world.post(instanceid=uuid.uuid4(), body={"reason": 'death'})

    assert response.status_code == 400
    assert response.json['success'] is False
    assert world.events == []


def test_remove_missing_token_wins_over_invalid_body(world):
    world.add(MONSTER_ID)

    response = world.post(token=None, body={"reason": 'death'})

    assert response.status_code == 401
    assert world.events == []
    assert MONSTER_ID in world.creatures


#
# Failures: always a 500 (the resolver retries on 5xx only), never a 200
#
def test_remove_publish_failure_is_500_and_touches_nothing(world):
    world.add(MONSTER_ID)
    world.failures['publish'] = ConnectionError('redis down')

    response = world.post()

    assert response.status_code == 500
    assert response.json['success'] is False
    assert response.json['payload'] is None
    # The publish is the first side effect: no purge, no delete
    assert world.events == []
    assert MONSTER_ID in world.creatures


def test_remove_purge_failure_is_500_and_keeps_the_creature(world):
    world.add(MONSTER_ID)
    world.failures['purge'] = ConnectionError('redis down')

    response = world.post()

    assert response.status_code == 500
    assert response.json['success'] is False
    assert [event[0] for event in world.events] == ['publish']
    assert MONSTER_ID in world.creatures


def test_remove_retry_after_delete_failure_is_removed(world):
    world.add(MONSTER_ID, delete_error=RuntimeError('mongo down'))
    assert world.post().status_code == 500
    assert MONSTER_ID in world.creatures

    # The resolver retries once Mongo is back
    world.add(MONSTER_ID)
    response = world.post()

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    creature_json = json.dumps({"_id": str(MONSTER_ID), "name": 'Monster'})
    purge = ('purge', {"creatureuuid": MONSTER_ID, "instanceuuid": INSTANCE_ID})
    assert world.events == [
        _kill(creature_json), purge,
        _kill(creature_json), purge, ('delete', MONSTER_ID),
        ]
    assert MONSTER_ID not in world.creatures


#
# Corpse (ruling Q105, Lordslair 2026-10-29): every dead monster leaves one,
# with the monster id, so a resolver retry never makes a second one
#
def _body(by, assists=None):
    body = {
        "reason": 'death',
        "by": None if by is None else str(by),
        "at": '2026-10-29T00:00:00',
        "requestId": str(uuid.uuid4()),
        }
    if assists is not None:
        body['assists'] = [str(assist) for assist in assists]
    return body


def test_remove_leaves_one_corpse_with_the_monster_fields(world):
    killer = uuid.uuid4()
    world.add(MONSTER_ID)

    response = world.post(body=_body(killer))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    corpses = world.corpses()
    assert len(corpses) == 1
    corpse = corpses[0]
    assert corpse.id == MONSTER_ID
    assert corpse.account is None
    assert corpse.instance == INSTANCE_ID
    assert corpse.killer == killer
    assert (corpse.gender, corpse.level, corpse.name, corpse.race, corpse.rarity) == (
        True, 3, 'Monster', 11, 'Big')
    assert (corpse.x, corpse.y) == (4, 5)


def test_remove_without_killer_still_leaves_a_corpse(world):
    # Q105 point 5: no killer, the corpse exists all the same (nobody may skin it)
    world.add(MONSTER_ID)

    response = world.post(body=_body(None))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    corpses = world.corpses()
    assert len(corpses) == 1
    assert corpses[0].id == MONSTER_ID
    assert corpses[0].killer is None


def test_remove_repeated_call_is_gone_and_makes_no_second_corpse(world):
    world.add(MONSTER_ID)
    assert world.post().json['payload'] == {"result": 'removed'}

    response = world.post()

    assert response.json['payload'] == {"result": 'gone'}
    assert [corpse.id for corpse in world.corpses()] == [MONSTER_ID]


def test_remove_gone_leaves_no_corpse(world):
    world.add(MONSTER_ID, instance=OTHER_INSTANCE_ID)

    assert world.post().json['payload'] == {"result": 'gone'}
    assert world.post(creatureid=uuid.uuid4()).json['payload'] == {"result": 'gone'}

    assert world.corpses() == []


def test_remove_publish_failure_leaves_no_corpse(world):
    world.add(MONSTER_ID)
    world.failures['publish'] = ConnectionError('redis down')

    assert world.post().status_code == 500

    assert world.corpses() == []


def test_remove_purge_failure_leaves_no_corpse(world):
    # The corpse is saved after the purge: a retry can't revive a skinned one
    world.add(MONSTER_ID)
    world.failures['purge'] = ConnectionError('redis down')

    assert world.post().status_code == 500

    assert world.corpses() == []


def test_remove_retry_after_failure_past_the_corpse_leaves_one_corpse(world):
    killer = uuid.uuid4()
    world.add(MONSTER_ID, delete_error=RuntimeError('mongo down'))

    # The corpse is saved before the Creature delete: the failed call already left it
    assert world.post(body=_body(killer)).status_code == 500
    assert [corpse.id for corpse in world.corpses()] == [MONSTER_ID]

    # The resolver retries once Mongo is back: same corpse, saved again
    world.add(MONSTER_ID)
    response = world.post(body=_body(killer))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    corpses = world.corpses()
    assert [corpse.id for corpse in corpses] == [MONSTER_ID]
    assert corpses[0].killer == killer


#
# XP (utils/xp.py, designer notes 2026-11-06): each Singouin among the killer
# (`by`) and the assists gets its own gain, from its own level, and may level
# up. Granted once the monster is gone, so never twice. The arithmetic itself
# is covered by test_00_xp.py: here, a level 30 Medium monster against level
# 30 Singouins is worth 300 solo, 187 each for 2 (x1.25/2), 150 each for 3
#
@pytest.fixture
def xp(world):
    """ The world with a level 30 Medium monster and a Singouin maker. """
    world.add(MONSTER_ID, level=30, rarity='Medium')

    def singouin(level=30, xp=0):
        _id = uuid.uuid4()
        world.add(_id, account=uuid.uuid4(), level=level, xp=xp)
        return _id

    world.singouin = singouin
    world.state = lambda _id: (world.creatures[_id].level, world.creatures[_id].xp)
    return world


def test_xp_killer_alone(xp):
    killer = xp.singouin()

    response = xp.post(body=_body(killer))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    assert xp.state(killer) == (30, 300)


def test_xp_group_bonus_between_killer_and_assists(xp):
    killer, first, second = xp.singouin(), xp.singouin(), xp.singouin()

    xp.post(body=_body(killer, [first, second]))

    assert [xp.state(_id) for _id in (killer, first, second)] == [(30, 150)] * 3


def test_xp_assists_without_killer(xp):
    first, second = xp.singouin(), xp.singouin()

    xp.post(body=_body(None, [first, second]))

    assert [xp.state(first), xp.state(second)] == [(30, 187), (30, 187)]


def test_xp_killer_repeated_in_assists_counts_once(xp):
    killer, assist = xp.singouin(), xp.singouin()

    xp.post(body=_body(killer, [killer, assist, assist]))

    # Two players, not four
    assert [xp.state(killer), xp.state(assist)] == [(30, 187), (30, 187)]


def test_xp_each_gain_uses_its_own_level(xp):
    killer = xp.singouin(level=30)
    veteran = xp.singouin(level=50)

    xp.post(body=_body(killer, [veteran]))

    assert xp.state(killer) == (30, 187)
    # 30 is more than 10 levels below 50: 300 x 0.1 x 1.25 / 2 = 18.75
    assert xp.state(veteran) == (50, 18)


def test_xp_monsters_and_unknown_ids_get_nothing_and_are_not_counted(xp):
    killer = xp.singouin()
    other_monster = uuid.uuid4()
    xp.add(other_monster)

    response = xp.post(body=_body(killer, [other_monster, uuid.uuid4()]))

    assert response.status_code == 200
    # Solo gain: the group is the Singouins only
    assert xp.state(killer) == (30, 300)
    assert xp.creatures[other_monster].xp == 0


def test_xp_levels_up_and_keeps_the_excess(xp):
    # 1 431 to leave level 30: 1 331 + 300 = 1 631, so level 31 with 200
    killer = xp.singouin(level=30, xp=1331)

    xp.post(body=_body(killer))

    assert xp.state(killer) == (31, 200)


def test_xp_nothing_more_at_the_max_level(xp):
    killer = xp.singouin(level=100, xp=0)

    response = xp.post(body=_body(killer))

    assert response.status_code == 200
    assert xp.state(killer) == (100, 0)


@pytest.mark.parametrize('killer', ['none', 'monster'])
def test_xp_without_a_singouin_is_still_removed(xp, killer):
    by = None
    if killer == 'monster':
        by = uuid.uuid4()
        xp.add(by)

    response = xp.post(body=_body(by))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    assert MONSTER_ID not in xp.creatures
    if by is not None:
        assert xp.creatures[by].xp == 0


def test_xp_concurrent_kill_is_read_again_not_overwritten(xp):
    killer = xp.singouin(level=30, xp=1000)

    def other_kill():
        # Another kill lands between the route's read and its write
        xp.creatures[killer].xp += 300
    xp.hooks['before_write'] = [other_kill]

    xp.post(body=_body(killer))

    # 1 000 + 300 (the other kill) + 300 (this one) = 1 600: level 31 with 169
    assert xp.state(killer) == (31, 169)


def test_xp_endless_conflict_gives_up_and_keeps_the_200(xp):
    killer = xp.singouin(level=30, xp=0)

    def other_kill():
        xp.creatures[killer].xp += 1
    xp.hooks['before_write'] = [other_kill] * xp.route.XP_WRITE_ATTEMPTS

    response = xp.post(body=_body(killer))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    # Only the other kills' XP: this one's is lost, never written over theirs
    assert xp.state(killer) == (30, xp.route.XP_WRITE_ATTEMPTS)


def test_xp_failure_for_one_singouin_does_not_stop_the_others(xp):
    killer, assist = xp.singouin(), xp.singouin()
    xp.failures['xp_for'] = killer

    response = xp.post(body=_body(killer, [assist]))

    assert response.status_code == 200
    assert xp.state(killer) == (30, 0)
    assert xp.state(assist) == (30, 187)


def test_xp_failure_keeps_the_200(xp):
    killer = xp.singouin()
    xp.failures['xp'] = RuntimeError('mongo down')

    response = xp.post(body=_body(killer))

    # The remove is done: losing the XP never makes it a 500
    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    assert MONSTER_ID not in xp.creatures
    assert [corpse.id for corpse in xp.corpses()] == [MONSTER_ID]
    assert xp.state(killer) == (30, 0)


def test_xp_retry_after_removed_pays_nothing_more(xp):
    killer = xp.singouin()
    body = _body(killer)
    assert xp.post(body=body).json['payload'] == {"result": 'removed'}

    response = xp.post(body=body)

    assert response.json['payload'] == {"result": 'gone'}
    assert xp.state(killer) == (30, 300)


@pytest.mark.parametrize('failure', ['publish', 'purge', 'delete'])
def test_xp_retry_after_a_500_pays_once(xp, failure):
    killer = xp.singouin()
    if failure == 'delete':
        xp.add(MONSTER_ID, level=30, rarity='Medium', delete_error=RuntimeError('mongo down'))
    else:
        xp.failures[failure] = ConnectionError('redis down')
    body = _body(killer)

    assert xp.post(body=body).status_code == 500
    assert xp.state(killer) == (30, 0)

    # The resolver retries once the backend is back
    xp.failures.clear()
    xp.add(MONSTER_ID, level=30, rarity='Medium')
    assert xp.post(body=body).json['payload'] == {"result": 'removed'}

    assert xp.state(killer) == (30, 300)


#
# Highscores: +1 general.kill for the killer, +1 general.assist for each
# assist. Singouins only (they alone have a Highscore), once per kill
#
def test_highscores_killer_kill_assists_assist(xp):
    killer, first, second = xp.singouin(), xp.singouin(), xp.singouin()

    response = xp.post(body=_body(killer, [first, second]))

    assert response.status_code == 200
    assert xp.highscores[killer] == {'kill': 1, 'assist': 0}
    assert xp.highscores[first] == {'kill': 0, 'assist': 1}
    assert xp.highscores[second] == {'kill': 0, 'assist': 1}


def test_highscores_killer_repeated_in_assists_is_only_the_killer(xp):
    killer, assist = xp.singouin(), xp.singouin()

    xp.post(body=_body(killer, [killer, assist, assist]))

    assert xp.highscores[killer] == {'kill': 1, 'assist': 0}
    assert xp.highscores[assist] == {'kill': 0, 'assist': 1}


def test_highscores_assists_without_killer(xp):
    assist = xp.singouin()

    response = xp.post(body=_body(None, [assist]))

    assert response.status_code == 200
    assert xp.highscores[assist] == {'kill': 0, 'assist': 1}


def test_highscores_monsters_and_unknown_ids_count_nothing(xp):
    assist = xp.singouin()
    monster_killer = uuid.uuid4()
    xp.add(monster_killer)

    response = xp.post(body=_body(monster_killer, [assist, uuid.uuid4()]))

    assert response.status_code == 200
    assert monster_killer not in xp.highscores
    assert xp.highscores == {assist: {'kill': 0, 'assist': 1}}


def test_highscores_retry_after_removed_counts_nothing_more(xp):
    killer, assist = xp.singouin(), xp.singouin()
    body = _body(killer, [assist])
    assert xp.post(body=body).json['payload'] == {"result": 'removed'}

    assert xp.post(body=body).json['payload'] == {"result": 'gone'}

    assert xp.highscores[killer] == {'kill': 1, 'assist': 0}
    assert xp.highscores[assist] == {'kill': 0, 'assist': 1}


def test_highscores_retry_after_a_500_counts_once(xp):
    killer, assist = xp.singouin(), xp.singouin()
    xp.add(MONSTER_ID, level=30, rarity='Medium', delete_error=RuntimeError('mongo down'))
    body = _body(killer, [assist])

    assert xp.post(body=body).status_code == 500
    assert xp.highscores[killer] == {'kill': 0, 'assist': 0}

    xp.add(MONSTER_ID, level=30, rarity='Medium')
    assert xp.post(body=body).json['payload'] == {"result": 'removed'}

    assert xp.highscores[killer] == {'kill': 1, 'assist': 0}
    assert xp.highscores[assist] == {'kill': 0, 'assist': 1}


@pytest.mark.parametrize('counter', ['kill', 'assist'])
def test_highscores_failure_keeps_the_200_the_xp_and_the_other_counter(xp, counter):
    killer, assist = xp.singouin(), xp.singouin()
    xp.failures[counter] = RuntimeError('mongo down')

    response = xp.post(body=_body(killer, [assist]))

    assert response.status_code == 200
    assert response.json['payload'] == {"result": 'removed'}
    assert [xp.state(killer), xp.state(assist)] == [(30, 187), (30, 187)]
    other = 'assist' if counter == 'kill' else 'kill'
    expected = {'kill': {killer: 1}, 'assist': {assist: 1}}
    for _id, count in expected[other].items():
        assert xp.highscores[_id][other] == count
    for _id in expected[counter]:
        assert xp.highscores[_id][counter] == 0


def test_highscores_counted_when_the_xp_fails(xp):
    killer = xp.singouin()
    xp.failures['xp'] = RuntimeError('mongo down')

    xp.post(body=_body(killer))

    assert xp.state(killer) == (30, 0)
    assert xp.highscores[killer] == {'kill': 1, 'assist': 0}


#
# Instance close (utils/instance.py): the kill reaches the AI on its env channel
#
def test_instance_close_publishes_kill_on_env_channel(modules, corpse_model, monkeypatch):
    utils_instance = modules.utils_instance
    monkeypatch.setattr(utils_instance, 'CorpseDocument', corpse_model.CorpseDocument)
    events = []

    monster = types.SimpleNamespace(
        id=MONSTER_ID,
        to_json=lambda json_options=None: json.dumps({"_id": str(MONSTER_ID)}),
        delete=lambda: events.append(('delete', MONSTER_ID)),
        )
    # leave_instance() filters twice: the players (count 1, the leaver is the
    # last one), then the monsters to kill
    results = iter([
        types.SimpleNamespace(count=lambda: 1),
        [monster],
        ])
    monkeypatch.setattr(utils_instance, 'CreatureDocument', types.SimpleNamespace(
        objects=types.SimpleNamespace(filter=lambda query: next(results))))
    monkeypatch.setattr(utils_instance, 'r', types.SimpleNamespace(
        publish=lambda channel, data: events.append(('publish', channel, json.loads(data)))))
    monkeypatch.setattr(utils_instance, 'purge_creature_keys', lambda **kwargs: events.append(('purge', kwargs)))  # noqa: E501
    monkeypatch.setattr(utils_instance, 'purge_instance_keys', lambda **kwargs: events.append(('purge_instance', kwargs)))  # noqa: E501

    leaver = types.SimpleNamespace(id=SINGOUIN_ID, save=lambda: None)
    instance = types.SimpleNamespace(
        id=INSTANCE_ID,
        to_json=lambda json_options=None: json.dumps({"_id": str(INSTANCE_ID)}),
        delete=lambda: events.append(('delete', INSTANCE_ID)),
        )

    assert utils_instance.leave_instance(leaver, instance) == 'closed'

    assert events == [
        ('purge', {"creatureuuid": SINGOUIN_ID, "instanceuuid": INSTANCE_ID}),
        ('publish', PS_AI_CREATURE, {
            "action": 'kill',
            "instance": json.dumps({"_id": str(INSTANCE_ID)}),
            "creature": json.dumps({"_id": str(MONSTER_ID)}),
            }),
        ('purge', {"creatureuuid": MONSTER_ID, "instanceuuid": INSTANCE_ID}),
        ('delete', MONSTER_ID),
        ('delete', INSTANCE_ID),
        ('purge_instance', {"instanceuuid": INSTANCE_ID}),
        ]


#
# Instance close / leave and the Corpses (ruling Q105: a Corpse lasts until
# its instance closes)
#
@pytest.fixture
def leave(modules, corpse_model, monkeypatch):
    """
    Runs leave_instance() with Redis stubbed and no monster left. players is
    the player count leave_instance() reads: 1 closes the Instance, 2 leaves it.
    The Corpses are real documents on mongomock.
    """
    utils_instance = modules.utils_instance
    model = corpse_model
    monkeypatch.setattr(utils_instance, 'CorpseDocument', model.CorpseDocument)
    monkeypatch.setattr(utils_instance, 'InstanceDocument', types.SimpleNamespace(
        objects=lambda **kwargs: types.SimpleNamespace(update_one=lambda **kwargs: None)))
    monkeypatch.setattr(utils_instance, 'r', types.SimpleNamespace(publish=lambda channel, data: None))  # noqa: E501
    monkeypatch.setattr(utils_instance, 'purge_creature_keys', lambda **kwargs: None)
    monkeypatch.setattr(utils_instance, 'purge_instance_keys', lambda **kwargs: None)

    def corpse(instance):
        return model.CorpseDocument(
            gender=True, instance=instance, name='Monster', race=11,
            ).save().id

    def run(players):
        results = iter([types.SimpleNamespace(count=lambda: players), []])
        monkeypatch.setattr(utils_instance, 'CreatureDocument', types.SimpleNamespace(
            objects=types.SimpleNamespace(filter=lambda query: next(results))))
        leaver = types.SimpleNamespace(id=SINGOUIN_ID, save=lambda: None)
        instance = types.SimpleNamespace(id=INSTANCE_ID, delete=lambda: None)
        return utils_instance.leave_instance(leaver, instance)

    def corpses():
        return {document.id for document in model.CorpseDocument.objects()}

    return types.SimpleNamespace(corpse=corpse, run=run, corpses=corpses)


def test_instance_close_deletes_its_corpses_only(leave):
    leave.corpse(INSTANCE_ID)
    leave.corpse(INSTANCE_ID)
    elsewhere = leave.corpse(OTHER_INSTANCE_ID)

    assert leave.run(players=1) == 'closed'

    assert leave.corpses() == {elsewhere}


def test_instance_left_keeps_its_corpses(leave):
    kept = {leave.corpse(INSTANCE_ID), leave.corpse(INSTANCE_ID)}

    assert leave.run(players=2) == 'left'

    assert leave.corpses() == kept


#
# api/variables.py: the channel rule itself, matching ai/variables.py CREATURE_PATH
#
def _load_api_variables(monkeypatch):
    """
    Executes the real api/variables.py under a private name. Its only Mongo
    use is the metas, stubbed with one each (none would stop it at import);
    nothing is left in sys.modules.
    """
    stub = types.SimpleNamespace(
        to_mongo=lambda: types.SimpleNamespace(to_dict=lambda: {'_id': 1}),
        )
    meta = types.ModuleType('mongo.models.Meta')
    for name in ('MetaArmor', 'MetaRace', 'MetaRecipe', 'MetaWeapon'):
        setattr(meta, name, types.SimpleNamespace(objects=lambda: [stub]))
    monkeypatch.setitem(sys.modules, 'mongo.models.Meta', meta)
    monkeypatch.setenv('SEP_SECRET_KEY', 'unit-test-secret')

    path = os.path.join(LOCAL_PATH, 'variables.py')
    spec = importlib.util.spec_from_file_location('_api_variables_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ps_ai_creature_follows_api_env(monkeypatch):
    monkeypatch.setenv('API_ENV', 'DEV')
    assert _load_api_variables(monkeypatch).PS_AI_CREATURE == 'ai-creature-dev'


def test_ps_ai_creature_without_api_env_does_not_crash(monkeypatch):
    monkeypatch.delenv('API_ENV', raising=False)
    assert _load_api_variables(monkeypatch).PS_AI_CREATURE == 'ai-creature-none'


def test_api_env_unset_is_warned_at_startup(monkeypatch):
    from loguru import logger
    records = []
    sink = logger.add(lambda message: records.append(message.record), level='WARNING')
    try:
        monkeypatch.delenv('API_ENV', raising=False)
        _load_api_variables(monkeypatch)
        monkeypatch.setenv('API_ENV', 'DEV')
        _load_api_variables(monkeypatch)
    finally:
        logger.remove(sink)

    # Once, for the load without API_ENV only
    warned = [record for record in records if record['message'].startswith('API_ENV unset')]
    assert len(warned) == 1


#
# Isolation: runs last in this file, after every use of the fixtures
#
def test_isolation_leaves_no_stub_bound_module():
    for name in ISOLATED:
        parent, _, child = name.rpartition('.')
        current = sys.modules.get(name)
        assert getattr(current, 'CreatureDocument', 'real') is not None
        parent_module = sys.modules.get(parent)
        if parent_module is not None and hasattr(parent_module, child):
            assert getattr(parent_module, child) is current
