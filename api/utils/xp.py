# -*- coding: utf8 -*-

# Pure XP and level arithmetic (designer notes "Système de niveaux et d'XP",
# 2026-11-06): no database access, unit-tested in tests/test_00_xp.py. The
# rarity multipliers live in mongo.constants.CREATURE_RARITY (xp_mult). The
# database side lives in routes/internal/instance/remove.py (_grant_xp).
#
# A Creature stores `level` and `xp`, the XP gathered *within* its current
# level (not a running total): a level-up subtracts the threshold and keeps
# the excess. At LEVEL_MAX there is no more XP to gain and xp stays 0.
#
# Decimal everywhere: 1.3 * p**2 in floats lands on x.4999... or x.5000...1
# and would round the thresholds differently from the notes.

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from mongo.constants import CREATURE_RARITY

# Balancing parameters: the only values to change (notes, section 1)
LEVEL_MAX = 100                 # L
KILLS_AT_LEVEL_1 = Decimal(1)   # b: Medium kills to leave level 1
KILLS_PER_LEVEL = Decimal('0.13')  # k: extra kills needed at each level
XP_PER_MONSTER_LEVEL = Decimal(10)  # X: XP of a Medium monster, per monster level

# Kill rules (notes, section 6)
GAP_ABOVE_MAX = 5               # a monster counts as at most player level + 5
GAP_BELOW = 10                  # a monster more than 10 levels below...
GAP_BELOW_FACTOR = Decimal('0.1')  # ...is worth 10% of its XP
CAP_PER_KILL = Decimal('0.5')   # a kill gives at most half of the current bar...
# ...but never less than a same level Medium kill, solo, its bonus included
# (X * (p + solo bonus)): levels 1-8, where kills(p) < 2, would else pay that
# reference kill below its worth (Lordslair, 2026-11-06), and level 10 would
# lose part of its first solo bonus. Above, the half bar is always the larger.

# Bonuses (Lordslair, 2026-11-12): none below BONUS_FROM_LEVEL, solo or in a
# group, to make that level a milestone worth reaching
BONUS_FROM_LEVEL = 10
SOLO_LEVELS_PER_BONUS = 10      # solo: the monster counts 1 level higher per 10 player levels
GROUP_BONUS_PER_PLAYER = Decimal('0.05')  # group: +5% per teammate...
GROUP_BONUS_MAX = Decimal('0.25')         # ...up to +25% (6 players and more)


def solo_bonus(level: int) -> int:
    """
    Monster levels added to a solo kill: 1 per SOLO_LEVELS_PER_BONUS player
    levels (+1 at 10-19, +2 at 20-29...), none below BONUS_FROM_LEVEL. Between
    +5% and +10% of a same level kill, whatever the level.
    """
    if level < BONUS_FROM_LEVEL:
        return 0
    return level // SOLO_LEVELS_PER_BONUS


def group_bonus(level: int, players: int) -> Decimal:
    """
    Multiplier of a kill shared by `players` (before the split): +5% per
    teammate, at most +25%. 1 solo, and below BONUS_FROM_LEVEL.
    """
    if level < BONUS_FROM_LEVEL or players < 2:
        return Decimal(1)
    return 1 + min(GROUP_BONUS_PER_PLAYER * (players - 1), GROUP_BONUS_MAX)


def xp_required(level: int) -> int:
    """
    XP needed to go from `level` to `level + 1`, rounded half up:
    X * p * kills(p), with kills(p) = b + k * (p - 1). 0 at LEVEL_MAX and above.
    """
    if level >= LEVEL_MAX:
        return 0
    kills = KILLS_AT_LEVEL_1 + KILLS_PER_LEVEL * (level - 1)
    return int((XP_PER_MONSTER_LEVEL * level * kills).quantize(Decimal(1), ROUND_HALF_UP))


def xp_gain(player_level: int, monster_level: int, rarity: str, players: int) -> int:
    """
    XP one player gets for a kill, rounded down (notes, section 6, with the
    bonuses of 2026-11-12):
    1. the monster counts as at most player level + GAP_ABOVE_MAX;
    2. solo, plus solo_bonus() levels, after that limit: the bonus is kept
       against the strongest monsters;
    3. X * that level * the rarity multiplier;
    4. x GAP_BELOW_FACTOR if the (real) monster level is more than GAP_BELOW below;
    5. x group_bonus(), then split evenly between the players;
    6. capped at CAP_PER_KILL of the player's current bar, that cap being
       never below X * (player level + solo_bonus()): a same level Medium
       kill, solo, its bonus included.
    0 at LEVEL_MAX, or with no player. An unknown rarity raises KeyError.
    """
    if player_level >= LEVEL_MAX or players < 1:
        return 0
    effective_level = min(monster_level, player_level + GAP_ABOVE_MAX)
    if players == 1:
        effective_level += solo_bonus(player_level)
    # Through str(): Decimal(0.1) would carry the float's binary error
    multiplier = Decimal(str(CREATURE_RARITY[rarity]['xp_mult']))
    xp = XP_PER_MONSTER_LEVEL * effective_level * multiplier
    if monster_level < player_level - GAP_BELOW:
        xp *= GAP_BELOW_FACTOR
    xp = xp * group_bonus(player_level, players) / players
    cap = max(
        CAP_PER_KILL * xp_required(player_level),
        XP_PER_MONSTER_LEVEL * (player_level + solo_bonus(player_level)),
        )
    xp = min(xp, cap)
    return max(0, int(xp.to_integral_value(ROUND_FLOOR)))


def apply_xp(level: int, xp: int, gain: int) -> tuple:
    """
    (level, xp) after `gain` (notes, section 5): while xp reaches the current
    threshold, it is subtracted and the level goes up by one. The excess is
    kept, several levels at once are possible. At LEVEL_MAX, xp is 0.
    """
    xp += gain
    while level < LEVEL_MAX and xp >= xp_required(level):
        xp -= xp_required(level)
        level += 1
    if level >= LEVEL_MAX:
        xp = 0
    return level, xp
