"""IoTDBSignalStore.write (single-sample) + iterator read, via mocked session."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from phm_data_factory.models import SampleMetadata
from phm_data_factory.stores.iotdb.config import IoTDBConfig
from phm_data_factory.stores.iotdb.store import IoTDBSignalStore


# ---- mock IoTDB client objects (mirrors tests/test_iotdb.py) ----
class _Types:
    DOUBLE = "DOUBLE"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    INT64 = "INT64"
    INT32 = "INT32"


class _Encoding:
    GORILLA = "GORILLA"
    PLAIN = "PLAIN"


class _Compressor:
    SNAPPY = "SNAPPY"


class _Tablet:
    def __init__(self, device, measurements, data_types, values, timestamps):
        self.device = device
        self.measurements = measurements
        self.data_types = data_types
        self.values = values
        self.timestamps = timestamps


class _Session:
    def __init__(self):
        self.series = set()
        self.tablets = []
        self.records = []
        self.databases = []
        self.deleted = []

    def execute_non_query_statement(self, sql):
        self.databases.append(sql)

    def check_time_series_exists(self, path):
        return path in self.series

    def create_aligned_time_series(self, device, measurements, *args):
        self.series.update(f"{device}.{m}" for m in measurements)

    def insert_aligned_tablet(self, tablet):
        self.tablets.append(tablet)

    def insert_aligned_record(self, device, timestamp, measurements, types, values):
        self.records.append((device, timestamp, measurements, types, values))

    def delete_data_in_range(self, paths, start, end):
        self.deleted.append((tuple(paths), start, end))


def _patched_imports(monkeypatch):
    monkeypatch.setattr(
        "phm_data_factory.iotdb._imports",
        lambda: (object, _Types, _Encoding, _Compressor, _Tablet),
    )


def _record(sample_id="1", name="RM_001_CWRU", sample_length=12, channels=2):
    return SampleMetadata(
        sample_id=sample_id,
        name=name,
        sample_rate=12000.0,
        sample_length=sample_length,
        channels=channels,
    )


def _store(session):
    store = IoTDBSignalStore(IoTDBConfig(), None, availability_via_catalog=False)
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)
    return store


def test_write_single_sample_chunked(monkeypatch):
    _patched_imports(monkeypatch)
    session = _Session()
    store = _store(session)
    report = store.write(
        "1", np.arange(24, dtype=np.float64).reshape(12, 2), metadata=_record(), chunk_size=5
    )
    assert report["chunks"] == 3
    assert report["length"] == 12 and report["channels"] == 2
    assert report["device"] == "root.vibench.RM_001_CWRU.sample_1.signal"
    assert len(session.tablets) == 3
    assert session.tablets[0].measurements == ["ch_0", "ch_1"]
    assert any("sample_id" in rec[2] for rec in session.records)
    assert "CREATE DATABASE root.vibench" in session.databases


def test_write_mode_error_raises_when_sample_exists(monkeypatch):
    _patched_imports(monkeypatch)
    session = _Session()
    session.series.add("root.vibench.RM_001_CWRU.sample_1.signal.ch_0")
    store = _store(session)
    with pytest.raises(FileExistsError):
        store.write("1", np.zeros((12, 2)), metadata=_record())


def test_write_mode_overwrite_clears_first(monkeypatch):
    _patched_imports(monkeypatch)
    session = _Session()
    session.series.add("root.vibench.RM_001_CWRU.sample_1.signal.ch_0")
    session.series.add("root.vibench.RM_001_CWRU.sample_1.signal.ch_1")
    store = _store(session)
    store.write("1", np.zeros((12, 2)), metadata=_record(), mode="overwrite")
    # overwrite must delete the existing signal data range before re-writing
    assert session.deleted
    paths = session.deleted[0][0]
    assert any(p.endswith(".ch_0") for p in paths)


def test_write_mode_overwrite_clears_metadata(monkeypatch):
    _patched_imports(monkeypatch)
    session = _Session()
    store = _store(session)
    store.write("1", np.zeros((12, 2)), metadata=_record(), mode="overwrite")

    deleted_paths = [path for paths, _, _ in session.deleted for path in paths]
    assert "root.vibench.RM_001_CWRU.sample_1.meta.sample_id" in deleted_paths
    assert (
        "root.vibench.RM_001_CWRU.sample_1.meta.digital_twin_prediction"
        in deleted_paths
    )


def test_write_rejects_metadata_length_mismatch(monkeypatch):
    _patched_imports(monkeypatch)
    store = _store(_Session())
    with pytest.raises(ValueError, match="sample_length"):
        store.write("1", np.zeros((4, 2)), metadata=_record())


def test_write_rejects_metadata_channel_mismatch(monkeypatch):
    _patched_imports(monkeypatch)
    store = _store(_Session())
    with pytest.raises(ValueError, match="channels"):
        store.write("1", np.zeros((12, 1)), metadata=_record())


def test_write_invalidates_lazy_catalog(monkeypatch):
    """After write, an IoTDB-backed (lazy) store must reload metadata on next
    access so it sees the freshly written sample."""
    _patched_imports(monkeypatch)
    session = _Session()
    store = IoTDBSignalStore(IoTDBConfig(), None, availability_via_catalog=True)
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)
    store.write("7", np.zeros((4, 2)), metadata=_record("7", sample_length=4))
    assert store._resolved is False
    assert store.metadata is None  # forces reload on next contains/shape/read


class _FrameResult:
    def __init__(self, frame):
        self._frame = frame

    def todf(self):
        return self._frame

    def close_operation_handle(self):
        pass


def test_delete_clears_metadata_and_invalidates_catalog(monkeypatch):
    _patched_imports(monkeypatch)

    class _DeleteSession(_Session):
        def execute_query_statement(self, sql):
            return _FrameResult(pd.DataFrame())

    session = _DeleteSession()
    store = IoTDBSignalStore(
        IoTDBConfig(), _catalog(), availability_via_catalog=True
    )
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)

    store.delete("1")

    deleted_paths = [path for paths, _, _ in session.deleted for path in paths]
    assert "root.vibench.RM_001_CWRU.sample_1.meta.sample_id" in deleted_paths
    assert store.contains("1") is False


# ---- iterator read (replaces todf) ----
class _Field:
    def __init__(self, v):
        self._v = v

    def is_null(self):
        return self._v is None

    def get_double_value(self):
        return float(self._v)


class _Row:
    def __init__(self, vals):
        self._vals = vals

    def get_fields(self):
        return [_Field(v) for v in self._vals]


class _IterResult:
    def __init__(self, rows):
        self._rows = list(rows)
        self._i = 0

    def has_next(self):
        return self._i < len(self._rows)

    def next(self):
        row = _Row(self._rows[self._i])
        self._i += 1
        return row

    def close_operation_handle(self):
        pass


def _catalog():
    from phm_data_factory.metadata import MetadataCatalog

    frame = pd.DataFrame(
        [
            {
                "Id": "1",
                "Name": "RM_001_CWRU",
                "Sample_rate": 12000.0,
                "Sample_lenth": 12,
                "Channel": 2,
            }
        ]
    )
    return MetadataCatalog(frame)


def test_read_uses_iterator_into_numpy(monkeypatch):
    _patched_imports(monkeypatch)
    rows = [[float(i), float(i) * 2] for i in range(12)]
    session = SimpleNamespace(
        execute_query_statement=lambda sql: _IterResult(rows),
    )
    store = IoTDBSignalStore(IoTDBConfig(), _catalog(), availability_via_catalog=False)
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)

    out = store.read("1", 0, 12)
    assert out.shape == (12, 2)
    assert out.dtype == np.float64
    np.testing.assert_allclose(out[:, 0], np.arange(12, dtype=np.float64))
    np.testing.assert_allclose(out[:, 1], np.arange(12, dtype=np.float64) * 2)


def test_read_respects_step_and_channels(monkeypatch):
    _patched_imports(monkeypatch)
    rows = [[float(i), float(i) * 10, float(i) * 100] for i in range(9)]
    session = SimpleNamespace(execute_query_statement=lambda sql: _IterResult(rows))
    # catalog says 3 channels for this test
    from phm_data_factory.metadata import MetadataCatalog

    cat = MetadataCatalog(
        pd.DataFrame([{"Id": "1", "Name": "X", "Sample_lenth": 9, "Channel": 3}])
    )
    store = IoTDBSignalStore(IoTDBConfig(), cat, availability_via_catalog=False)
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)

    out = store.read("1", 0, 9, channels=[0, 2], step=3)
    assert out.shape == (3, 2)  # 9//3 rows, 2 selected channels
    np.testing.assert_allclose(out[:, 0], [0.0, 3.0, 6.0])
    np.testing.assert_allclose(out[:, 1], [0.0, 30.0, 60.0])
