from __future__ import annotations

import json
import shutil

import pytest

from phm_data_factory import AgentDataTools, PHMDataRepository
from phm_data_factory.identity import (
    build_dataset_identity,
    validate_dataset_identity,
)
from phm_data_factory.iotdb import IoTDBConfig, IoTDBSignalStore, build_source_manifest
from phm_data_factory.metadata import MetadataCatalog
from phm_data_factory.models import SampleMetadata
from phm_data_factory.stores.iotdb.schema import (
    METADATA_SCHEMA_VERSION,
    decode_metadata,
    encode_metadata,
)
from phm_data_factory.stores.iotdb.metadata import _catalog_from_session


def test_agent_manifest_supports_static_and_concrete_runtime(repository):
    static = AgentDataTools.manifest()
    assert static["api_schema_version"] == "1.0.0"
    assert static["backend_kind"] == "runtime_selected"

    tools = AgentDataTools(
        repository,
        profile="benchmark_public",
        backend_kind="local_hdf5",
        dataset_digest="sha256:fixture",
    )
    runtime = tools.manifest()
    assert runtime["package_version"] == "0.2.1"
    assert runtime["backend_kind"] == "local_hdf5"
    assert runtime["dataset_digest"] == "sha256:fixture"
    assert (
        runtime["capabilities"]["label_visibility_policy"]
        == "public_evaluator_private_v1"
    )


def test_benchmark_public_redacts_labels_and_rejects_private_filters(repository):
    tools = AgentDataTools(repository, profile="benchmark_public")
    found = tools.search_samples(dataset_id=1, limit=2)
    described = tools.get_sample_metadata("1")
    assert found and "label" not in found[0] and "fault_level" not in found[0]
    assert "label" not in described and "rul_label" not in described
    with pytest.raises(ValueError):
        tools.search_samples(label=0)
    with pytest.raises(ValueError):
        tools.search_samples(extra_filters={"Label": 0})


def test_window_declares_dtype_modality_and_time_basis(repository):
    result = AgentDataTools(repository).get_signal_window("1", end=4)
    assert result["dtype"] == "float64"
    assert result["modality"] == "continuous_series"
    assert result["time_basis"] == "sample_index"


def test_phm_vibench_metadata_profile_preserves_scalar_types(repository):
    frame = repository.metadata_frame("phm_vibench_v1")
    assert list(frame["Id"]) == ["1", "2"]
    assert list(frame["Dataset_id"]) == [1, 1]
    assert list(frame["Label"]) == [0, 1]
    assert list(frame["Domain_id"]) == [0, 1]


def test_dataset_identity_is_path_independent(local_data, tmp_path):
    metadata, signals = local_data
    other = tmp_path / "relocated"
    other.mkdir()
    metadata_copy = other / metadata.name
    signals_copy = other / signals.name
    shutil.copy2(metadata, metadata_copy)
    shutil.copy2(signals, signals_copy)
    first = build_dataset_identity(build_source_manifest(metadata, signals), ["2", "1"])
    second = build_dataset_identity(
        build_source_manifest(metadata_copy, signals_copy), ["1", "2"]
    )
    assert first["dataset_digest"] == second["dataset_digest"]
    assert "path" not in json.dumps(first)
    tampered = dict(first)
    tampered["sample_ids"] = ["1"]
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_dataset_identity(tampered)


def test_typed_metadata_payload_round_trip():
    record = SampleMetadata(
        sample_id="7",
        dataset_id=3,
        label=2,
        domain_id=1,
        visible=True,
        extra={"nested": {"enabled": True}, "weights": [1, 2.5]},
    )
    payload = encode_metadata(record)
    decoded = decode_metadata(payload)
    rebuilt = SampleMetadata.from_mapping(decoded)
    assert rebuilt.dataset_id == 3
    assert rebuilt.label == 2
    assert rebuilt.extra["nested"] == {"enabled": True}
    assert METADATA_SCHEMA_VERSION.endswith("v2")


def test_metadata_sync_path_does_not_write_signals(monkeypatch, local_data):
    metadata, _ = local_data
    catalog = MetadataCatalog.from_file(metadata)
    store = IoTDBSignalStore(
        IoTDBConfig(), catalog, availability_via_catalog=False
    )
    seen = []
    monkeypatch.setattr(store, "contains", lambda sample_id: True)
    monkeypatch.setattr(store, "ensure_database", lambda: None)
    monkeypatch.setattr(store, "_write_metadata", lambda record: seen.append(record))
    store.write_metadata(catalog.raw("1"))
    assert [record.sample_id for record in seen] == ["1"]


def test_iotdb_loader_prefers_typed_v2_payload():
    payload = encode_metadata(
        SampleMetadata(
            sample_id="7", dataset_id=3, label=2, domain_id=1, visible=True
        )
    )

    class Result:
        def todf(self):
            import pandas as pd

            return pd.DataFrame(
                [
                    {
                        "Device": "root.vibench.fixture.sample_7.meta",
                        "root.vibench.fixture.sample_7.meta.sample_id": "7",
                        "root.vibench.fixture.sample_7.meta.metadata_schema_version": METADATA_SCHEMA_VERSION,
                        "root.vibench.fixture.sample_7.meta.metadata_json": payload,
                    }
                ]
            )

        def close_operation_handle(self):
            pass

    class Session:
        def execute_query_statement(self, sql):
            assert "ALIGN BY DEVICE" in sql
            return Result()

    catalog = _catalog_from_session(IoTDBConfig(), Session())
    assert catalog is not None
    assert catalog.fidelity == "lossless_v2"
    frame = catalog.to_frame("phm_vibench_v1")
    assert frame.iloc[0]["Dataset_id"] == 3
    assert frame.iloc[0]["Label"] == 2


def test_phm_vibench_profile_rejects_indexed_v1_metadata():
    catalog = MetadataCatalog(
        __import__("pandas").DataFrame(
            [{"sample_id": "1", "dataset_id": "3", "label": "2"}]
        ),
        "sample_id",
        fidelity="indexed_v1",
    )
    with pytest.raises(ValueError, match="sync-metadata"):
        catalog.to_frame("phm_vibench_v1")
