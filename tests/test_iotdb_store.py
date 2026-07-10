from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from phm_data_factory.iotdb import IoTDBConfig, IoTDBSignalStore
from phm_data_factory.models import SampleMetadata


class _MetadataResult:
    def __init__(self, frame):
        self.frame = frame
        self.closed = False

    def todf(self):
        return self.frame.copy()

    def close_operation_handle(self):
        self.closed = True


class _Field:
    def __init__(self, value):
        self.value = value

    def get_double_value(self):
        return self.value


class _Row:
    def __init__(self, values):
        self.values = values

    def get_fields(self):
        return [_Field(value) for value in self.values]


class _IteratorResult:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.current = None
        self.closed = False

    def has_next(self):
        try:
            self.current = next(self.rows)
            return True
        except StopIteration:
            return False

    def next(self):
        return _Row(self.current)

    def close_operation_handle(self):
        self.closed = True


def _metadata_frame():
    return pd.DataFrame(
        [
            {
                "Time": 0,
                "Device": "root.vibench.RM_001_CWRU.sample_1.meta",
                "root.vibench.RM_001_CWRU.sample_1.meta.sample_id": "1",
                "root.vibench.RM_001_CWRU.sample_1.meta.name": "RM_001_CWRU",
                "root.vibench.RM_001_CWRU.sample_1.meta.sample_length": 4,
                "root.vibench.RM_001_CWRU.sample_1.meta.channels": 2,
                "root.vibench.RM_001_CWRU.sample_1.meta.sample_rate": 12000.0,
            }
        ]
    )


def test_db_backed_index_and_iterator_read_without_xlsx():
    metadata_result = _MetadataResult(_metadata_frame())
    iterator_result = _IteratorResult([[10.0], [11.0], [12.0], [13.0]])

    class Session:
        def __init__(self):
            self.queries = []

        def execute_query_statement(self, sql):
            self.queries.append(sql)
            if ".meta ALIGN BY DEVICE" in sql:
                return metadata_result
            return iterator_result

    session = Session()
    store = IoTDBSignalStore(IoTDBConfig(), metadata=None)
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)

    assert store.list_ids() == ("1",)
    assert store.contains("1") is True
    assert store.contains("missing") is False
    assert store.shape("1") == (4, 2)
    values = store.read("1", start=0, end=4, channels=[1], step=2)
    np.testing.assert_array_equal(values, [[10.0], [12.0]])
    assert sum(".meta ALIGN BY DEVICE" in query for query in session.queries) == 1
    assert metadata_result.closed and iterator_result.closed


def test_write_publishes_metadata_after_all_tablets(monkeypatch):
    events = []

    class Types:
        DOUBLE = "DOUBLE"
        TEXT = "TEXT"
        BOOLEAN = "BOOLEAN"
        INT64 = "INT64"
        INT32 = "INT32"

    class Encoding:
        GORILLA = "GORILLA"
        PLAIN = "PLAIN"

    class Compressor:
        SNAPPY = "SNAPPY"

    class Tablet:
        def __init__(self, device, measurements, data_types, values, timestamps):
            self.device = device
            self.measurements = measurements
            self.values = values
            self.timestamps = timestamps

    class Session:
        def __init__(self):
            self.series = set()

        def execute_non_query_statement(self, sql):
            events.append(("database", sql))

        def check_time_series_exists(self, path):
            return path in self.series

        def create_aligned_time_series(self, device, names, *args):
            self.series.update(f"{device}.{name}" for name in names)

        def insert_aligned_tablet(self, tablet):
            events.append(("tablet", tablet))

        def insert_aligned_record(self, *args):
            events.append(("metadata", args))

    monkeypatch.setattr(
        "phm_data_factory.iotdb._imports",
        lambda: (object, Types, Encoding, Compressor, Tablet),
    )
    session = Session()
    store = IoTDBSignalStore(IoTDBConfig())
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)
    record = SampleMetadata(
        sample_id="new",
        name="RM_NEW",
        sample_rate=1000,
        digital_twin_prediction=True,
    )
    report = store.write(
        "new",
        np.arange(12, dtype=float).reshape(6, 2),
        metadata=record,
        chunk_size=4,
        mode="upsert",
    )
    assert report["chunks"] == 2
    kinds = [event[0] for event in events]
    assert kinds.index("metadata") > max(i for i, kind in enumerate(kinds) if kind == "tablet")
    metadata_event = next(event for event in events if event[0] == "metadata")
    assert "digital_twin_prediction" in metadata_event[1][2]
