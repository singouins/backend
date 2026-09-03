# -*- coding: utf8 -*-

import time

from variables import r


def test_singouins_redis_connection():
    assert r.ping()


def test_singouins_redis_set():
    assert r.set('test_singouins', 'OK', ex=1)


def test_singouins_redis_get():
    assert r.get('test_singouins')


def test_singouins_redis_expired():
    time.sleep(1)
    assert not r.get('test_singouins')
