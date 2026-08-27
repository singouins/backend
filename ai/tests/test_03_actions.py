# -*- coding: utf8 -*-

"""
Fast, isolated unit tests for the reconciler in ai/utils/actions.py.

No live Mongo/Redis/Flask stack needed - these exercise reconcile_threads()
directly against fake Mob-like objects with a controllable task.done(), the
same way test_02_computation.py mocks out CreatureDocument.
"""

from types import SimpleNamespace

from utils.actions import reconcile_threads


class FakeTask:
    """Stand-in for the asyncio.Task stored as Mob.task, with a fixed done()."""

    def __init__(self, done):
        self._done = done

    def done(self):
        return self._done


class FakeMob:
    """Stand-in for a bestiaire Mob with a controllable task.done()."""

    def __init__(self, creature_id, name, race, alive):
        self.creature = SimpleNamespace(id=creature_id, name=name, race=race)
        self.task = FakeTask(done=not alive)


def test_reconcile_threads_prunes_only_dead_entries():
    alive = FakeMob('c1', 'Alive One', race=14, alive=True)
    dead = FakeMob('c2', 'Dead One', race=14, alive=False)
    threads = [alive, dead]

    pruned = reconcile_threads(threads)

    assert pruned == 1
    assert threads == [alive]


def test_reconcile_threads_returns_zero_when_nothing_died():
    alive = FakeMob('c1', 'Alive One', race=14, alive=True)
    threads = [alive]

    pruned = reconcile_threads(threads)

    assert pruned == 0
    assert threads == [alive]


def test_reconcile_threads_handles_multiple_dead_entries():
    threads = [
        FakeMob('c1', 'Dead A', race=14, alive=False),
        FakeMob('c2', 'Alive', race=15, alive=True),
        FakeMob('c3', 'Dead B', race=15, alive=False),
        ]

    pruned = reconcile_threads(threads)

    assert pruned == 2
    assert len(threads) == 1
    assert threads[0].creature.name == 'Alive'


def test_reconcile_threads_leaves_empty_list_untouched():
    threads = []

    pruned = reconcile_threads(threads)

    assert pruned == 0
    assert threads == []
