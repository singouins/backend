# -*- coding: utf8 -*-

from decimal import Decimal
import os
import sys

import pytest

# Needed for local imports and simulate production paths (api/ on sys.path,
# resolved from this file so it works whatever the cwd pytest runs from)
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.append(LOCAL_PATH)

from utils.xp import (  # noqa: E402
    LEVEL_MAX,
    apply_xp,
    group_bonus,
    solo_bonus,
    xp_gain,
    xp_required,
    )

# Designer notes "Système de niveaux et d'XP" (2026-11-06). Pure unit tests:
# no Mongo, no Redis.


#
# xp_required(p) = round(10 * p * (1 + 0.13 * (p - 1)))
#
@pytest.mark.parametrize('level, required', [
    (1, 10),
    (2, 23),        # 22.6
    (3, 38),        # 37.8
    (10, 217),
    (30, 1431),
    (31, 1519),
    (50, 3685),
    (75, 7965),     # the notes' table says 7 976: their own formula gives 7 965
    (99, 13603),    # 13 602.6
    ])
def test_xp_required_matches_the_notes(level, required):
    assert xp_required(level) == required


@pytest.mark.parametrize('level', [LEVEL_MAX, LEVEL_MAX + 1])
def test_xp_required_is_zero_at_the_max_level(level):
    assert xp_required(level) == 0


def test_xp_required_grows_with_the_level():
    required = [xp_required(level) for level in range(1, LEVEL_MAX)]
    assert required == sorted(required)
    assert len(set(required)) == len(required)


def test_xp_to_reach_the_max_level_matches_the_notes():
    # Sum of the rounded thresholds, as the notes compute it
    assert sum(xp_required(level) for level in range(1, LEVEL_MAX)) == 469940


#
# Bonuses: none below level 10. Solo, +1 monster level per 10 player levels;
# in a group, +5% per teammate up to +25%, before the split
#
@pytest.mark.parametrize('level, bonus', [
    (1, 0),
    (9, 0),
    (10, 1),
    (19, 1),
    (20, 2),
    (55, 5),
    (99, 9),
    ])
def test_solo_bonus_one_level_per_ten(level, bonus):
    assert solo_bonus(level) == bonus


@pytest.mark.parametrize('level', range(10, LEVEL_MAX))
def test_solo_bonus_is_five_to_ten_percent_of_a_same_level_kill(level):
    assert 0.05 < solo_bonus(level) / level <= 0.10


@pytest.mark.parametrize('players, bonus', [
    (1, 1),
    (2, '1.05'),
    (3, '1.10'),
    (5, '1.20'),
    (6, '1.25'),
    (8, '1.25'),   # at most +25%
    ])
def test_group_bonus_five_percent_per_teammate(players, bonus):
    assert group_bonus(30, players) == Decimal(bonus)


@pytest.mark.parametrize('players', [1, 2, 6])
def test_group_bonus_none_below_level_10(players):
    assert group_bonus(9, players) == 1


#
# xp_gain(player level, monster level, rarity, players)
#
def test_gain_same_level_medium_solo():
    # The monster counts as level 33: +3 for a level 30 Singouin alone
    assert xp_gain(30, 30, 'Medium', 1) == 330


@pytest.mark.parametrize('level, gain', [
    (9, 90),      # no bonus below level 10
    (10, 110),    # +1, paid in full: the cap floor includes it
    (19, 200),
    (20, 220),
    (99, 1080),
    ])
def test_gain_solo_bonus(level, gain):
    assert xp_gain(level, level, 'Medium', 1) == gain


@pytest.mark.parametrize('rarity, gain', [
    ('Small', 165),
    ('Medium', 330),
    ('Big', 660),
    ('Unique', 715),   # 1 320, capped at half of 1 431
    ('Boss', 715),
    ('God', 715),
    ])
def test_gain_rarity_multiplier(rarity, gain):
    assert xp_gain(30, 30, rarity, 1) == gain


@pytest.mark.parametrize('monster_level, gain', [
    (54, 283),   # 540 * 1.05 / 2 = 283.5
    (55, 288),   # 550 * 1.05 / 2 = 288.75
    (56, 288),   # counts as 55: player level + 5
    (80, 288),
    ])
def test_gain_monster_above_counts_as_five_levels_more_at_most(monster_level, gain):
    # In a group of 2: no solo bonus to blur the limit
    assert xp_gain(50, monster_level, 'Medium', 2) == gain


@pytest.mark.parametrize('monster_level, gain', [
    (54, 590),   # 54 + 5
    (55, 600),
    (56, 600),   # limited to 55, then + 5: the solo bonus is kept
    (80, 600),
    ])
def test_gain_solo_bonus_comes_after_the_limit_above(monster_level, gain):
    assert xp_gain(50, monster_level, 'Medium', 1) == gain


@pytest.mark.parametrize('monster_level, gain', [
    (41, 460),   # counts as 41 + 5 (solo)
    (40, 450),   # exactly 10 below: no penalty
    (39, 44),    # more than 10 below (the real level): 10% of 440
    (1, 6),
    ])
def test_gain_monster_far_below_is_worth_ten_percent(monster_level, gain):
    assert xp_gain(50, monster_level, 'Medium', 1) == gain


@pytest.mark.parametrize('players, gain', [
    (1, 550),   # solo: 55 levels, not a group bonus
    (2, 262),   # 500 * 1.05 / 2 = 262.5, rounded down
    (3, 183),   # 500 * 1.10 / 3 = 183.3
    (4, 143),   # 500 * 1.15 / 4 = 143.75
    (6, 104),   # 500 * 1.25 / 6 = 104.2
    (8, 78),    # 500 * 1.25 / 8: no more than +25%
    ])
def test_gain_group_bonus(players, gain):
    assert xp_gain(50, 50, 'Medium', players) == gain


@pytest.mark.parametrize('players, gain', [
    (1, 90),
    (2, 45),    # an even split, nothing more
    (3, 30),
    ])
def test_gain_no_bonus_below_level_10(players, gain):
    assert xp_gain(9, 9, 'Medium', players) == gain


def test_gain_group_bonus_from_level_10():
    assert xp_gain(10, 10, 'Medium', 2) == 52   # 100 * 1.05 / 2 = 52.5


def test_gain_is_capped_at_half_a_bar():
    # Level 10: the monster counts as level 15 + 1, 160 XP, capped at 110
    # (217 / 2 = 108.5, below the floor: a same level Medium kill, solo, +1)
    assert xp_gain(10, 50, 'Medium', 1) == 110
    # Level 20: 25 + 2 levels, 270 XP, under half a bar (347)
    assert xp_gain(20, 50, 'Medium', 1) == 270
    # Level 9: half a bar (92) is above a same level Medium kill (90)
    assert xp_gain(9, 14, 'God', 1) == 92


@pytest.mark.parametrize('level', range(1, 9))
def test_gain_cap_is_never_below_a_same_level_medium_kill(level):
    # Levels 1-8: half a bar is less than X * p, the cap is X * p instead
    assert xp_required(level) / 2 < 10 * level
    assert xp_gain(level, level, 'Medium', 1) == 10 * level
    # A rarer or higher monster gets no more than that
    assert xp_gain(level, level + 5, 'God', 1) == 10 * level


def test_gain_cap_floor_keeps_rare_monsters_from_skipping_levels():
    # A God 5 levels above a level 1 player is worth 960: one level, not nine
    assert apply_xp(1, 0, xp_gain(1, 6, 'God', 1)) == (2, 0)


def test_kills_per_level_follow_the_curve_at_low_levels():
    # Same level Medium kills, solo, to leave each level: ceil(kills(p))
    kills = [
        -(-xp_required(level) // xp_gain(level, level, 'Medium', 1))
        for level in range(1, 10)
        ]
    assert kills == [1, 2, 2, 2, 2, 2, 2, 2, 3]


@pytest.mark.parametrize('player_level', [LEVEL_MAX, LEVEL_MAX + 1])
def test_gain_is_zero_at_the_max_level(player_level):
    assert xp_gain(player_level, player_level, 'God', 1) == 0


def test_gain_is_zero_without_players():
    assert xp_gain(30, 30, 'Medium', 0) == 0


def test_gain_unknown_rarity_raises():
    with pytest.raises(KeyError):
        xp_gain(30, 30, 'Legendary', 1)


#
# apply_xp(level, xp in the level, gain) -> (level, xp in the level)
#
@pytest.mark.parametrize('level, xp, gain, expected', [
    (1, 0, 0, (1, 0)),
    (1, 0, 5, (1, 5)),
    (1, 5, 5, (2, 0)),            # exactly the bar
    (1, 9, 10, (2, 9)),           # the excess is kept
    (1, 0, 10 + 23 + 5, (3, 5)),  # two levels at once
    (30, 1331, 300, (31, 200)),
    (99, 13600, 10, (LEVEL_MAX, 0)),        # the excess is dropped at the max
    (LEVEL_MAX, 0, 50, (LEVEL_MAX, 0)),     # nothing more to gain
    ])
def test_apply_xp(level, xp, gain, expected):
    assert apply_xp(level, xp, gain) == expected


def test_apply_xp_whole_curve():
    assert apply_xp(1, 0, 469940) == (LEVEL_MAX, 0)
    assert apply_xp(1, 0, 469939) == (99, 13602)
