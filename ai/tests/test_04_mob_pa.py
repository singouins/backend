# -*- coding: utf8 -*-

"""
Mob.get_pa(): one FCALL_RO pa_read (library functions_pa), as the API,
discord and the resolver read the PA pools. No live Redis needed: the
client is mocked, the pa_read arithmetic itself is tested in api/tests
(fakeredis + the library copy).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bestiaire._Mob import Mob
from variables import env_vars


def _mob(tick):
    return SimpleNamespace(
        creature=SimpleNamespace(id='c0fe'),
        instance=SimpleNamespace(tick=tick),
        logh='[test]',
        )


def test_get_pa_reads_through_functions_pa():
    mob = _mob(tick=3600)
    # {red_pa, red_ttnpa, red_ttl, blue_pa, blue_ttnpa, blue_ttl}
    fake = AsyncMock()
    fake.fcall_ro.return_value = [14, 1400, 5000, 6, 1800, 9000]

    with patch('bestiaire._Mob.r', fake):
        asyncio.run(Mob.get_pa(mob))

    fake.fcall_ro.assert_awaited_once_with(
        'pa_read', 2,
        f"{env_vars['API_ENV']}:pas:c0fe:blue",
        f"{env_vars['API_ENV']}:pas:c0fe:red",
        3600, 7200, 16, 8,
        )
    assert (mob.pa.red, mob.pa.blue) == (14, 6)


def test_get_pa_uses_the_instance_tick():
    mob = _mob(tick=60)
    fake = AsyncMock()
    fake.fcall_ro.return_value = [16, 0, -2, 8, 0, -2]

    with patch('bestiaire._Mob.r', fake):
        asyncio.run(Mob.get_pa(mob))

    assert fake.fcall_ro.await_args.args[4:] == (60, 120, 16, 8)
    assert (mob.pa.red, mob.pa.blue) == (16, 8)


def test_get_pa_redis_error_falls_back_to_full_pools():
    """ A Redis hiccup (or a missing library) never crashes the Creature task. """
    mob = _mob(tick=3600)
    fake = AsyncMock()
    fake.fcall_ro.side_effect = Exception('ERR Function not found')

    with patch('bestiaire._Mob.r', fake):
        asyncio.run(Mob.get_pa(mob))

    assert (mob.pa.red, mob.pa.blue) == (16, 8)
