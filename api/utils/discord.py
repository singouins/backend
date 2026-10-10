# -*- coding: utf8 -*-

# Discord queue scopes for a creature. Kept free of any mongo import so it
# can be unit-tested offline with plain fakes.
#
# CreatureKorp.id and CreatureSquad.id are UUIDField(default=None): the
# embedded documents always carry an `id` attribute, so the check is on its
# value, not on its presence.
#
# A Pending invitee is not a member: an invite sets the id together with
# rank='Pending', and such a creature gets no scope for that group. Korp and
# Squad are checked independently. A missing rank counts as a member.


def discord_scopes(creature) -> list:
    scopes = []
    korp = getattr(creature, 'korp', None)
    korp_id = getattr(korp, 'id', None)
    if korp_id is not None and getattr(korp, 'rank', None) != 'Pending':
        scopes.append(f'Korp-{korp_id}')
    squad = getattr(creature, 'squad', None)
    squad_id = getattr(squad, 'id', None)
    if squad_id is not None and getattr(squad, 'rank', None) != 'Pending':
        scopes.append(f'Squad-{squad_id}')
    return scopes
