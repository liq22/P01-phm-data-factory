from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from phm_data_factory.iotdb import (
    IoTDBConfig,
    IoTDBImporter,
    IoTDBPathCodec,
    build_source_manifest,
)
from phm_data_factory.models import SampleMetadata


def test_iotdb_path_codec_is_stable_and_readable():
    config = IoTDBConfig(root="root.vibench")
    record = SampleMetadata(sample_id="1", name="RM_001_CWRU")
    assert (
        IoTDBPathCodec.signal_device(config, record)
        == "root.vibench.RM_001_CWRU.sample_1.signal"
    )
    special = SampleMetadata(sample_id="a/b", name="Pump #1")
    path = IoTDBPathCodec.signal_device(config, special)
    assert path.startswith("root.vibench.Pump_1_")
    assert ".sample_a_b_" in path


def test_importer_uses_aligned_chunked_writes(repository, monkeypatch):
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
            self.data_types = data_types
            self.values = values
            self.timestamps = timestamps

    class Session:
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
            self.series.update(
                f"{device}.{measurement}" for measurement in measurements
            )

        def insert_aligned_tablet(self, tablet):
            self.tablets.append(tablet)

        def insert_aligned_record(self, device, timestamp, measurements, types, values):
            self.records.append((device, timestamp, measurements, types, values))

    session = Session()
    connection = SimpleNamespace(open=lambda: session, close=lambda: None)
    monkeypatch.setattr(
        "phm_data_factory.iotdb._imports",
        lambda: (object, Types, Encoding, Compressor, Tablet),
    )
    importer = IoTDBImporter(IoTDBConfig())
    importer.connection = connection
    report = importer.import_sample(repository, 1, chunk_size=5)

    assert report["chunks"] == 3
    assert len(session.tablets) == 3
    assert session.tablets[0].measurements == ["ch_0", "ch_1"]
    assert any("sample_id" in record[2] for record in session.records)
    assert "CREATE DATABASE root.vibench" in session.databases


def test_import_repository_includes_iotdb_data_manifest(repository, monkeypatch):
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
            self.data_types = data_types
            self.values = values
            self.timestamps = timestamps

    class Session:
        def execute_non_query_statement(self, sql):
            del sql

        def check_time_series_exists(self, path):
            del path
            return False

        def create_aligned_time_series(self, *args):
            del args

        def insert_aligned_tablet(self, tablet):
            del tablet

        def insert_aligned_record(self, *args):
            del args

    monkeypatch.setattr(
        "phm_data_factory.iotdb._imports",
        lambda: (object, Types, Encoding, Compressor, Tablet),
    )
    importer = IoTDBImporter(IoTDBConfig(root="root.paper"))
    importer.connection = SimpleNamespace(open=Session, close=lambda: None)
    report = importer.import_repository(
        repository,
        sample_ids=["1"],
        chunk_size=5,
        source_manifest={"metadata": {"sha256": "metadata-digest"}},
    )

    manifest = report["data_manifest"]
    assert manifest["schema_version"] == "phm-data-factory/iotdb-data-manifest-v2"
    assert manifest["root"] == "root.paper"
    assert manifest["path_model"] == "tree"
    assert manifest["source"]["metadata"]["sha256"] == "metadata-digest"
    assert manifest["imported_sample_ids"] == ["1"]
    assert manifest["failed_sample_ids"] == []


def test_source_manifest_hashes_metadata_and_signal_files(local_data):
    metadata, signals = local_data
    manifest = build_source_manifest(metadata, signals)
    assert manifest["metadata"]["sha256"]
    assert manifest["signals"]["kind"] == "file"
    assert manifest["signals"]["sha256"]
