# -*- coding: utf8 -*-

import asyncio
import json

import main

# Real Redis outages (e.g. Redis restarting, a network blip) can't be
# simulated safely against the shared Redis instance the rest of this test
# suite runs against, so this exercises the retry/backoff logic directly:
# the listener's underlying Redis client is swapped for a fake that fails
# on its first connection attempt(s) and recovers afterwards, mirroring a
# transient Redis hiccup.


class _FakePubSub:
    def __init__(self, should_fail):
        self.should_fail = should_fail

    async def subscribe(self, *_args, **_kwargs):
        if self.should_fail:
            raise main.redis.RedisError('simulated Redis hiccup')

    psubscribe = subscribe

    async def listen(self):
        if self.should_fail:
            raise main.redis.RedisError('simulated Redis hiccup')
        yield {'type': 'message', 'data': b'{"hello": "world"}'}
        # Stay "connected" afterwards, like a real, still-open pub/sub does.
        await asyncio.Event().wait()


class _FlakyRedis:
    """Fails the first `fail_attempts` connections, then works normally."""

    fail_attempts = 1
    attempts = 0

    def __init__(self, *_args, **_kwargs):
        pass

    def pubsub(self):
        cls = type(self)
        cls.attempts += 1
        return _FakePubSub(should_fail=cls.attempts <= cls.fail_attempts)


class _AlwaysFailingRedis(_FlakyRedis):
    fail_attempts = float('inf')


class _FakeClient:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


async def _drive_listener_until_message(timeout=2):
    fake_client = _FakeClient()
    main.CLIENTS.add(fake_client)
    task = asyncio.create_task(main.listen_to_broadcast())
    try:
        waited = 0
        while not fake_client.sent and waited < timeout:
            await asyncio.sleep(0.01)
            waited += 0.01
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        main.CLIENTS.discard(fake_client)
    return fake_client.sent, task


def test_listener_recovers_after_a_redis_hiccup(monkeypatch):
    _FlakyRedis.attempts = 0
    monkeypatch.setattr(main.redis, 'Redis', _FlakyRedis)
    monkeypatch.setattr(main, 'RECONNECT_DELAY', 0.01)
    monkeypatch.setattr(main, 'RECONNECT_DELAY_MAX', 0.01)

    sent, task = asyncio.run(_drive_listener_until_message())

    # The first connection attempt failed, yet the listener reconnected on
    # its own and still delivered the message - it did not crash/propagate.
    assert _FlakyRedis.attempts > 1
    assert sent == [json.dumps({"hello": "world"})]
    assert task.cancelled()  # we stopped it; it never raised on its own


def test_listener_keeps_retrying_through_sustained_failure(monkeypatch):
    _AlwaysFailingRedis.attempts = 0
    monkeypatch.setattr(main.redis, 'Redis', _AlwaysFailingRedis)
    monkeypatch.setattr(main, 'RECONNECT_DELAY', 0.01)
    monkeypatch.setattr(main, 'RECONNECT_DELAY_MAX', 0.01)

    async def _run():
        task = asyncio.create_task(main.listen_to_broadcast())
        await asyncio.sleep(0.2)
        still_running = not task.done()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return still_running

    still_running = asyncio.run(_run())

    # Even with Redis never coming back, the listener keeps retrying instead
    # of raising out of asyncio.gather() and killing the whole service.
    assert still_running
    assert _AlwaysFailingRedis.attempts > 1
