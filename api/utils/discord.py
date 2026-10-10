# -*- coding: utf8 -*-

# Discord queue scopes for a creature. Kept free of any mongo import so it
# can be unit-tested offline with plain fakes.
#
# CreatureKorp.id and CreatureSquad.id are UUIDField(default=None): the
# embedded documents always carry an `id` attribute, so the check is on its
# value, not on its presence.


def discord_scopes(creature) -> list:
    scopes = []
    korp_id = getattr(getattr(creature, 'korp', None), 'id', None)
    if korp_id is not None:
        scopes.append(f'Korp-{korp_id}')
    squad_id = getattr(getattr(creature, 'squad', None), 'id', None)
    if squad_id is not None:
        scopes.append(f'Squad-{squad_id}')
    return scopes
