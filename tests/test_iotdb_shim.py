"""Back-compat shim: re-exports + _imports monkeypatch propagation to store.write."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import phm_data_factory.iotdb as shim
from phm_data_factory import iotdb
from phm_data_factory.models import SampleMetadata
from phm_data_factory.stores.iotdb.store import IoTDBSignalStore


PUBLIC_SYMBOLS = [
    "IoTDBConfig",
    "IoTDBPathCodec",
    "IoTDBSession",
    "load_metadata_from_iotdb",
    "IoTDBSignalStore",
    "IoTDBImporter",
    "build_source_manifest",
    "build_iotdb_data_manifest",
    "main",
    "_resolve_iotdb_config",
    "_probe_socket",
    "_imports",
]


def test_shim_reexports_every_public_symbol():
    for name in PUBLIC_SYMBOLS:
        assert hasattr(shim, name), f"shim missing {name}"


def test_iotdb_importable_as_module_attribute():
    # tests/test_iotdb_cli.py does `from phm_data_factory import iotdb`
    assert iotdb is shim


def test_schema_has_digital_twin_prediction():
    fields = [n for n, _ in shim.IoTDBImporter.SCHEMA]
    assert "digital_twin_prediction" in fields
    assert "sample_id" in fields


def test_imports_monkeypatch_propagates_to_store_write(monkeypatch):
    """The load-bearing back-compat guarantee: a test patching
    ``phm_data_factory.iotdb._imports`` must affect ``IoTDBSignalStore.write``
    (because the store resolves _imports through the shim at call time)."""

    class _Types:
        DOUBLE = "DOUBLE"
        TEXT = "TEXT"
        BOOLEAN = "BOOLEAN"
        INT64 = "INT64"
        INT32 = "INT32"

    class _Enc:
        GORILLA = "G"
        PLAIN = "P"

    class _Comp:
        SNAPPY = "S"

    class _SentinelTablet:
        def __init__(self, *a, **k):
            self.args = a

    monkeypatch.setattr(
        "phm_data_factory.iotdb._imports",
        lambda: (object, _Types, _Enc, _Comp, _SentinelTablet),
    )

    class _Session:
        def __init__(self):
            self.series = set()
            self.tablets = []
            self.records = []
            self.databases = []

        def execute_non_query_statement(self, sql):
            self.databases.append(sql)

        def check_time_series_exists(self, path):
            return path in self.series

        def create_aligned_time_series(self, device, measurements, *args):
            self.series.update(f"{device}.{m}" for m in measurements)

        def insert_aligned_tablet(self, tablet):
            self.tablets.append(tablet)

        def insert_aligned_record(self, *args):
            self.records.append(args)

    session = _Session()
    store = IoTDBSignalStore(shim.IoTDBConfig(), None, availability_via_catalog=False)
    store.connection = SimpleNamespace(open=lambda: session, close=lambda: None)
    store.write(
        "1",
        np.arange(12, dtype=np.float64).reshape(6, 2),
        metadata=SampleMetadata(sample_id="1", name="X"),
        chunk_size=3,
    )
    # the patched _SentinelTablet must be the one used
    assert session.tablets and isinstance(session.tablets[0], _SentinelTablet)
    assert len(session.tablets) == 2  # 6 rows / chunk 3
