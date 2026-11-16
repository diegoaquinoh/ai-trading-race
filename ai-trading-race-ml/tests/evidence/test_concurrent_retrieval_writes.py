"""Concurrent identical retrievals must not fail on the content-addressed insert race.

Regression: two strategies with the same evidence access (llm_graph and llm_team) issue
the same retrieval at the same cutoff in parallel decision requests. Both writers passed
the existence check and the loser hit an IntegrityError, which surfaced as a
``failed_dependency`` decision. The writer now retries and verifies the committed payload.
"""

from datetime import datetime, timezone

import pytest

from research_engine.contracts.evidence import RetrievalRequest
from research_engine.evidence.store import ImmutableRecordConflict
from research_engine.retrieval import retrieve


class _InsertInterceptingConnection:
    """Proxy that runs ``before_insert`` right before the first INSERT statement."""

    def __init__(self, conn, before_insert):
        self._conn = conn
        self._before_insert = before_insert

    def execute(self, statement, *args, **kwargs):
        if self._before_insert is not None and getattr(statement, "is_insert", False):
            hook, self._before_insert = self._before_insert, None
            hook()
        return self._conn.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _request(index, question: str) -> RetrievalRequest:
    return RetrievalRequest(
        question=question,
        decision_as_of=datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc),
        mode="hybrid_rag_v1",
        index_build_id=index.build_id,
    )


def test_identical_concurrent_write_is_tolerated(home, default_index, monkeypatch):
    store = home.store
    request = _request(default_index, "concurrent writer race on the policy rate statement")
    run, bundle = retrieve(request, store, default_index)  # first write commits normally

    original = store._insert_immutable
    raced = {"armed": True}

    def racing_insert(table, pk, rows, conn):
        if table == "retrieval_runs" and raced["armed"]:
            raced["armed"] = False
            payload_rows = rows

            def concurrent_writer():
                # Another writer commits the identical record between check and insert.
                with store.engine.begin() as other:
                    other.execute(
                        store.tbl(table).delete().where(store.tbl(table).c[pk] == rows[0][pk])
                    )
                with store.engine.begin() as other:
                    original(table, pk, payload_rows, other)

            # Remove the committed row so this writer's existence check misses it, then let
            # the concurrent writer re-insert it right before this writer's INSERT.
            with store.engine.begin() as other:
                other.execute(
                    store.tbl(table).delete().where(store.tbl(table).c[pk] == rows[0][pk])
                )
            return original(table, pk, rows, _InsertInterceptingConnection(conn, concurrent_writer))
        return original(table, pk, rows, conn)

    monkeypatch.setattr(store, "_insert_immutable", racing_insert)
    store.put_retrieval(run, bundle, datetime(2026, 11, 10, tzinfo=timezone.utc), 1)

    assert raced["armed"] is False, "the race was not exercised"
    assert store.get_retrieval_run(run.retrieval_run_id) == run


def test_conflicting_payload_still_raises(home, default_index):
    store = home.store
    run, bundle = retrieve(
        _request(default_index, "immutable conflict probe for the balance sheet runoff"),
        store,
        default_index,
    )
    tampered = run.model_copy(update={"snapshot_chunk_count": run.snapshot_chunk_count + 1})
    with pytest.raises(ImmutableRecordConflict):
        store.put_retrieval(tampered, bundle, datetime(2026, 11, 10, tzinfo=timezone.utc), 1)
