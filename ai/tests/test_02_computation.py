# -*- coding: utf8 -*-

"""
Fast, isolated unit tests for ai/utils/computation.py.

These do not need a live Mongo/Redis/Flask stack (unlike
test_01_ai_creature.py) - they exercise the pure movement/collision math
directly and mock out the single Mongo call `is_coords_empty` makes, so
they run in milliseconds and catch regressions in this logic on their own
(e.g. the is_coords_empty() bug where `.filter()` is lazy and never
raises, so the function always reported every tile as occupied).
"""

from types import SimpleNamespace
from unittest.mock import patch

from utils.computation import (
    closest_player_from_me,
    is_coords_empty,
    next_coords_to_creature,
    )


def _mob(x, y, mob_id='self-id', p=0):
    creature = SimpleNamespace(
        x=x, y=y, id=mob_id,
        stats=SimpleNamespace(total=SimpleNamespace(p=p)),
        )
    return SimpleNamespace(creature=creature, logh='[test]')


def _target(x, y):
    return SimpleNamespace(x=x, y=y)


def _creature(x, y, race, creature_id):
    return SimpleNamespace(x=x, y=y, race=race, id=creature_id)


# next_coords_to_creature

def test_next_coords_moves_one_step_towards_target_on_both_axes():
    mob = _mob(x=0, y=0)
    target = _target(x=5, y=5)
    assert next_coords_to_creature(mob, target) == (1, 1)


def test_next_coords_moves_one_step_away_when_target_is_behind():
    mob = _mob(x=5, y=5)
    target = _target(x=0, y=0)
    assert next_coords_to_creature(mob, target) == (4, 4)


def test_next_coords_stays_put_on_axis_already_adjacent():
    # Target is already exactly 1 tile away on X: should not overshoot onto it
    mob = _mob(x=5, y=0)
    target = _target(x=6, y=0)
    assert next_coords_to_creature(mob, target) == (5, 0)


def test_next_coords_stays_put_when_already_on_same_tile_axis():
    mob = _mob(x=3, y=3)
    target = _target(x=3, y=3)
    assert next_coords_to_creature(mob, target) == (3, 3)


# is_coords_empty

def test_is_coords_empty_true_when_no_creature_on_tile():
    mob = _mob(x=1, y=1)
    with patch('utils.computation.CreatureDocument') as MockDoc:
        MockDoc.objects.filter.return_value.count.return_value = 0
        assert is_coords_empty(mob, x=1, y=1) is True


def test_is_coords_empty_false_when_a_creature_is_on_the_tile():
    mob = _mob(x=1, y=1)
    with patch('utils.computation.CreatureDocument') as MockDoc:
        MockDoc.objects.filter.return_value.count.return_value = 1
        assert is_coords_empty(mob, x=1, y=1) is False


def test_is_coords_empty_returns_none_on_query_error():
    mob = _mob(x=1, y=1)
    with patch('utils.computation.CreatureDocument') as MockDoc:
        MockDoc.objects.filter.side_effect = Exception('boom')
        assert is_coords_empty(mob, x=1, y=1) is None


# closest_player_from_me
#
# Regression coverage for the self.stats bug: `self` here is the Mob
# thread instance, which only ever sets self.creature/self.instance/
# self.pa/self.logh - self.stats does not exist. This used to crash with
# AttributeError as soon as the range calculation ran.

def test_closest_player_from_me_uses_creature_stats_not_self_stats():
    # p=100 -> range = 4 + round(100/50) = 6. Would raise AttributeError
    # before the fix (self.stats.total.p instead of self.creature.stats.total.p).
    mob = _mob(x=0, y=0, p=100)
    target = _target(x=1, y=1)
    with patch('utils.computation.CreatureDocument') as MockDoc:
        qs = MockDoc.objects.filter.return_value
        qs.count.return_value = 1
        qs.get.return_value = target
        assert closest_player_from_me(mob) is target


def test_closest_player_from_me_picks_the_nearest_player_and_skips_self_and_npcs():
    mob = _mob(x=0, y=0, mob_id='self-id')
    me = _creature(x=0, y=0, race=14, creature_id='self-id')       # self - must be skipped
    other_npc = _creature(x=1, y=0, race=14, creature_id='npc-id')  # another NPC - must be skipped
    far_player = _creature(x=10, y=10, race=1, creature_id='far-id')
    near_player = _creature(x=1, y=1, race=1, creature_id='near-id')

    with patch('utils.computation.CreatureDocument') as MockDoc:
        qs = MockDoc.objects.filter.return_value
        qs.count.return_value = 4
        qs.__iter__.return_value = iter([me, other_npc, far_player, near_player])
        assert closest_player_from_me(mob) is near_player


def test_closest_player_from_me_returns_none_when_nothing_in_range():
    mob = _mob(x=0, y=0)
    with patch('utils.computation.CreatureDocument') as MockDoc:
        qs = MockDoc.objects.filter.return_value
        qs.count.return_value = 0
        qs.__iter__.return_value = iter([])
        assert closest_player_from_me(mob) is None
