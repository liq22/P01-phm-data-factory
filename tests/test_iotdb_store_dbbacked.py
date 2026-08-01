"""DB-backed IoTDBSignalStore: reads work with metadata=None (no local xlsx)."""
from __future__ import annotations

import pandas as pd
from types import SimpleNamespace

from phm_data_factory.stores.iotdb.config import IoTDBConfig
from phm_data_factory.stores.iotdb.store import IoTDBSignalStore


class _FrameResult:
    """Mimics iotdb SessionDataSet for the todf() path."""

    def __init__(self, frame):
        self._frame = frame

    def todf(self):
        return self._frame

    def close_operation_handle(self):
        pass


def _meta_frame():
    return pd.DataFrame(
        [
            {
                "Time": 0,
                "Device": "root.vibench.RM_001_CWRU.sample_1.meta",
                "sample_id": "1",
                "name": "RM_001_CWRU",
                "sample_length": 12,
                "channels": 2,
                "sample_rate": 12000.0,
            },
            {
                "Time": 0,
                "Device": "root.vibench.RM_001_CWRU.sample_2.meta",
                "sample_id": "2",
                "name": "RM_001_CWRU",
                "sample_length": 8,
                "channels": 1,
                "sample_rate": 12000.0,
            },
        ]
    )


def _store_with_session(route):
    """Build a store with metadata=None and an injected session whose
    execute_query_statement(sql) is routed by `route(sql)` -> _FrameResult."""
    config = IoTDBConfig(root="root.vibench")
    store = IoTDBSignalStore(config, None)  # availability_via_catalog defaults True
    session = SimpleNamespace(execute_query_statement=lambda sql: route(sql))
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)
    return store


def test_list_ids_contains_shape_without_xlsx():
    store = _store_with_session(
        lambda sql: _FrameResult(_meta_frame()) if "ALIGN BY DEVICE" in sql else _FrameResult(pd.DataFrame())
    )
    assert set(store.list_ids()) == {"1", "2"}
    assert store.contains("1") is True
    assert store.contains("missing") is False
    assert store.shape("1") == (12, 2)
    assert store.availability_is_cheap is True  # O(1) catalog membership


def test_shape_falls_back_to_count_when_meta_lacks_length():
    meta = pd.DataFrame(
        [
            {
                "Time": 0,
                "Device": "root.vibench.X.sample_9.meta",
                "sample_id": "9",
                "name": "X",
            }
        ]
    )
    count_frame = pd.DataFrame({"count": [42]})

    class _Sess:
        def execute_query_statement(self, sql):
            if "ALIGN BY DEVICE" in sql:
                return _FrameResult(meta)
            if "COUNT" in sql:
                return _FrameResult(count_frame)
            return _FrameResult(pd.DataFrame())

        def check_time_series_exists(self, path):
            # ch_0 and ch_1 exist, ch_2 does not
            return path.endswith("ch_0") or path.endswith("ch_1")

    store = IoTDBSignalStore(IoTDBConfig(root="root.vibench"), None)
    store.connection = SimpleNamespace(open=lambda: _Sess(), close=lambda: None)
    assert store.shape("9") == (42, 2)


def test_empty_db_yields_no_samples():
    store = _store_with_session(
        lambda sql: _FrameResult(pd.DataFrame())  # empty meta
    )
    assert tuple(store.list_ids()) == ()
    assert store.contains("1") is False
