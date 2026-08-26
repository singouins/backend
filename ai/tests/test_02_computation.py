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

from utils.computation import is_coords_empty, next_coords_to_creature


def _mob(x, y):
    return SimpleNamespace(creature=SimpleNamespace(x=x, y=y), logh='[test]')


def _target(x, y):
    return SimpleNamespace(x=x, y=y)


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
