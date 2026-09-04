# -*- coding: utf8 -*-

import os
import sys
import urllib.parse
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from mongoengine import connect

# main.py's package-relative imports (mongo.models.*, subcommands.*,
# subtasks.*, variables) only resolve when discord/ itself is on the path -
# same trick ws/tests/conftest.py uses.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# MongoDB variables (mirrors api/tests/conftest.py / mongo/tests connection
# setup, kept in sync intentionally rather than shared, since each service's
# test suite is meant to be runnable standalone)
MONGO_BASE = os.environ.get("MONGO_BASE", 'singouins')
MONGO_HOST = os.environ.get("MONGO_HOST", '127.0.0.1')
MONGO_PASS = os.environ.get("MONGO_PASS")
MONGO_USER = os.environ.get("MONGO_USER", 'singouins')

username = urllib.parse.quote_plus(MONGO_USER)
password = urllib.parse.quote_plus(MONGO_PASS or '')

if os.environ.get("CI"):
    # Inside GitHub CI / a throwaway single-node Mongo container: no replicas.
    MONGO_CONN = 'mongodb'
    MONGO_REPL = ''
    MONGO_STLS = ''
else:
    MONGO_CONN = 'mongodb+srv'
    MONGO_REPL = '&replicaSet=replicaset'
    MONGO_STLS = '&tls=true'

MONGO_URI = '%s://%s:%s@%s/%s?authSource=admin%s%s' % (
    MONGO_CONN,
    username,
    password,
    MONGO_HOST,
    MONGO_BASE,
    MONGO_REPL,
    MONGO_STLS,
    )

# `variables.py` queries the MetaArmor/MetaWeapon/MetaRace collections at
# *import* time (see discord/variables.py), and every subcommand module
# imports `variables`. So the Mongo connection has to exist before pytest
# imports any test module that pulls in `subcommands.*` - conftest.py is
# always imported first, so doing it here at module level (not inside a
# fixture) is the only place that's early enough.
connect(host=MONGO_URI, uuidRepresentation='standard')

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("API_ENV", "test")

import discord  # noqa: E402

from mongo.models.Creature import (  # noqa: E402
    CreatureDocument,
    CreatureHP,
    CreatureKorp,
    CreatureSlots,
    CreatureSquad,
    CreatureStats,
    CreatureStatsType,
    )
from mongo.models.Highscore import (  # noqa: E402
    HighscoreDocument,
    HighscoreGeneral,
    HighscoreInternal,
    HighscoreInternalGenericResource,
    HighscoreProfession,
    )
from mongo.models.Item import ItemDocument  # noqa: E402
from mongo.models.Meta import MetaArmor  # noqa: E402
from mongo.models.Satchel import (  # noqa: E402
    SatchelAmmo,
    SatchelCurrency,
    SatchelDocument,
    SatchelResource,
    SatchelShard,
    )
from mongo.models.User import UserDocument  # noqa: E402

# Deterministic Meta reference data for tests that price/describe items.
# Seeded here (module level, before any subcommand import) so it's present
# by the time `variables.py` builds its metaIndexed dict.
MetaArmor(_id=1, name='Test Armor', size='2x2', tier=1).save()


@pytest.fixture(autouse=True)
def _clean_db():
    """Every test starts from an empty (non-Meta) database."""
    yield
    CreatureDocument.drop_collection()
    HighscoreDocument.drop_collection()
    ItemDocument.drop_collection()
    SatchelDocument.drop_collection()
    UserDocument.drop_collection()


@pytest.fixture
async def bot():
    # Must be constructed from inside a running event loop - discord.Bot()
    # grabs the current one at __init__ time, and pytest-asyncio only
    # guarantees one exists inside an async fixture/test, not during
    # ordinary sync fixture setup.
    intents = discord.Intents.default()
    return discord.Bot(intents=intents)


@pytest.fixture
def make_ctx():
    """Build a stand-in for discord.ApplicationContext.

    Real pycord objects need a live gateway connection to construct, so
    this only fills in what the command callbacks actually touch:
    ctx.channel.name/type, ctx.author.*, ctx.guild.roles, and the async
    ctx.respond()/ctx.author.add_roles()/ctx.author.send() calls.
    """
    def _make_ctx(*, author_name='tester', channel_name='general', channel_type=None, guild_roles=None):  # noqa: E501
        roles = list(guild_roles or [])
        ctx = MagicMock()
        ctx.channel.name = channel_name
        ctx.channel.type = channel_type or discord.ChannelType.text
        ctx.author.name = author_name
        ctx.author.roles = []
        ctx.author.guild.roles = roles
        ctx.guild.roles = roles
        ctx.author.add_roles = AsyncMock()
        ctx.author.send = AsyncMock()
        ctx.respond = AsyncMock()
        return ctx
    return _make_ctx


@pytest.fixture
def get_callback():
    """Grab a registered slash-command's callback by name.

    Calling it directly (bypassing group.invoke()) skips Discord's own
    transport and the @commands.guild_only()/@has_any_role() checks -
    intentional, since those aren't the business logic under test here.
    """
    def _get_callback(group, name):
        for command in group.walk_commands():
            if command.name == name:
                return command.callback
        raise LookupError(f'No command named {name!r} registered on {group!r}')
    return _get_callback


# --- Document factories -----------------------------------------------
# Real Mongo documents (not mocks), so assertions can reload() and check
# what actually got persisted - that's what would have caught bugs like
# the missing Highscore.save() this suite grew out of.

@pytest.fixture
def make_user():
    def _make_user(**overrides):
        data = dict(
            _id=uuid.uuid4(),
            active=True,
            discord={'name': 'tester', 'ack': False},
            hash='hashed',
            name='tester',
            )
        data.update(overrides)
        return UserDocument(**data).save()
    return _make_user


@pytest.fixture
def make_creature():
    def _make_creature(**overrides):
        data = dict(
            gender=True,
            hp=CreatureHP(),
            korp=CreatureKorp(),
            name=f'creature-{uuid.uuid4()}',
            race=1,
            slots=CreatureSlots(),
            squad=CreatureSquad(),
            stats=CreatureStats(
                race=CreatureStatsType(),
                spec=CreatureStatsType(),
                total=CreatureStatsType(),
                ),
            )
        data.update(overrides)
        return CreatureDocument(**data).save()
    return _make_creature


@pytest.fixture
def make_satchel():
    def _make_satchel(**overrides):
        data = dict(
            ammo=SatchelAmmo(),
            currency=SatchelCurrency(),
            resource=SatchelResource(),
            shard=SatchelShard(),
            )
        data.update(overrides)
        return SatchelDocument(**data).save()
    return _make_satchel


@pytest.fixture
def make_highscore():
    def _make_highscore(**overrides):
        data = dict(
            general=HighscoreGeneral(),
            internal=HighscoreInternal(
                fur=HighscoreInternalGenericResource(),
                item=HighscoreInternalGenericResource(),
                leather=HighscoreInternalGenericResource(),
                meat=HighscoreInternalGenericResource(),
                ore=HighscoreInternalGenericResource(),
                shard=HighscoreInternalGenericResource(),
                skin=HighscoreInternalGenericResource(),
                ),
            profession=HighscoreProfession(),
            )
        data.update(overrides)
        return HighscoreDocument(**data).save()
    return _make_highscore


@pytest.fixture
def make_item():
    def _make_item(**overrides):
        data = dict(
            bearer=uuid.uuid4(),
            metaid=1,
            metatype='armor',
            )
        data.update(overrides)
        return ItemDocument(**data).save()
    return _make_item
