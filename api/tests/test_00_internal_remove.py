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
    'mongo.models.Instance': ['InstanceDocument'],
    'mongo.models.Item': ['ItemDocument'],
    'mongo.models.Korp': ['KorpDocument'],
    'mongo.models.Squad': ['SquadDocument'],
    'mongo.models.User': ['UserDocument'],
    }
ISOLATED = [
    'routes.internal',
    'routes.internal.instance',
    'utils.decorators',
    'utils.instance',
    ]
_ABSENT = object()


@pytest.fixture
def modules(monkeypatch):
    """
    Imports routes.internal.instance and utils.instance against stubbed models,
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
        import routes.internal.instance as route
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
    Its 'from mongo.utils import utcnow' gets mongo/utils.py under a stub
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


class _Collection:
    """ Stands for Document.objects: objects(_id=x).first() reads a dict by id. """
    def __init__(self, documents):
        self.documents = documents

    def __call__(self, _id=None, **kwargs):
        return types.SimpleNamespace(first=lambda: self.documents.get(_id))


def _document(events, store, _id, instance, account=None, delete_error=None):
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
        level=3,
        name='Monster',
        race=11,
        rarity='Big',
        x=4,
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
    an exception make that call raise instead. Corpses are real documents on
    mongomock, read back with corpses().
    """
    route = modules.route
    monkeypatch.setattr(route, 'CorpseDocument', corpse_model.CorpseDocument)
    events = []
    creatures = {}
    instances = {
        INSTANCE_ID: types.SimpleNamespace(
            id=INSTANCE_ID,
            to_json=lambda json_options=None: json.dumps({"_id": str(INSTANCE_ID)}),
            ),
        }
    monkeypatch.setattr(route, 'CreatureDocument', types.SimpleNamespace(objects=_Collection(creatures)))  # noqa: E501
    monkeypatch.setattr(route, 'InstanceDocument', types.SimpleNamespace(objects=_Collection(instances)))  # noqa: E501
    failures = {}

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

    def add(_id, instance=INSTANCE_ID, account=None, delete_error=None):
        creatures[_id] = _document(events, creatures, _id, instance, account, delete_error)
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
        failures=failures, corpses=corpses,
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
def _body(by):
    return {
        "reason": 'death',
        "by": None if by is None else str(by),
        "at": '2026-10-29T00:00:00',
        "requestId": str(uuid.uuid4()),
        }


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
    for name in ('MetaArmor', 'MetaRace', 'MetaWeapon'):
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
