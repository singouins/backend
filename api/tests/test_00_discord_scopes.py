# -*- coding: utf8 -*-

import os
import sys

from types import SimpleNamespace

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

from utils.discord import discord_scopes  # noqa: E402

# The embedded CreatureKorp / CreatureSquad always carry an `id` attribute
# (UUIDField(default=None)), so the fakes below keep `id=None` rather than
# dropping the attribute: that is what a creature without korp/squad looks
# like once loaded from Mongo.

KORP_ID = '11111111-1111-1111-1111-111111111111'
SQUAD_ID = '22222222-2222-2222-2222-222222222222'


def creature(korp_id=None, squad_id=None):
    return SimpleNamespace(
        korp=SimpleNamespace(id=korp_id, rank=None),
        squad=SimpleNamespace(id=squad_id, rank=None),
    )


def test_korp_and_squad():
    assert discord_scopes(creature(KORP_ID, SQUAD_ID)) == [
        f'Korp-{KORP_ID}',
        f'Squad-{SQUAD_ID}',
    ]


def test_korp_only():
    assert discord_scopes(creature(korp_id=KORP_ID)) == [f'Korp-{KORP_ID}']


def test_squad_only():
    # Regression: the Squad scope used to be gated on the korp
    assert discord_scopes(creature(squad_id=SQUAD_ID)) == [f'Squad-{SQUAD_ID}']


def test_neither():
    # Regression: hasattr(korp, 'id') was always true, giving 'Korp-None'
    assert discord_scopes(creature()) == []


def test_embedded_objects_none():
    assert discord_scopes(SimpleNamespace(korp=None, squad=None)) == []
