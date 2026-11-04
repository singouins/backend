# -*- coding: utf8 -*-

from unittest.mock import MagicMock, patch

from utils.redis import get_pa
from variables import env_vars


def test_get_pa_reads_through_functions_pa():
    """
    get_pa() is one FCALL_RO pa_read (library functions_pa): KEYS blue then red,
    ARGV red first (durations, then maxima), the reply mapped per colour.
    The pa_read arithmetic itself is tested in api/tests (fakeredis + library copy).
    """
    fake = MagicMock()
    # {red_pa, red_ttnpa, red_ttl, blue_pa, blue_ttnpa, blue_ttl}
    fake.fcall_ro.return_value = [14, 1400, 5000, 6, 1800, 9000]

    with patch('utils.redis.r', fake):
        pa = get_pa(creatureuuid='c0fe', tick=3600)

    fake.fcall_ro.assert_called_once_with(
        'pa_read', 2,
        f"{env_vars['API_ENV']}:pas:c0fe:blue",
        f"{env_vars['API_ENV']}:pas:c0fe:red",
        3600, 7200, 16, 8,
        )
    assert pa == {
        'blue': {'pa': 6, 'ttnpa': 1800, 'ttl': 9000},
        'red': {'pa': 14, 'ttnpa': 1400, 'ttl': 5000},
        }


def test_get_pa_fast_instance_durations():
    fake = MagicMock()
    fake.fcall_ro.return_value = [16, 0, -2, 8, 0, -2]

    with patch('utils.redis.r', fake):
        get_pa(creatureuuid='c0fe', tick=60)

    assert fake.fcall_ro.call_args.args[4:] == (60, 120, 16, 8)
