from __future__ import annotations

import os
from pathlib import Path

import pytest

from phm_data_factory import (
    AgentDataPort,
    AgentDataTools,
    PHMDataRepository,
    __version__,
)
from phm_data_factory.contract import PACKAGE_VERSION


PRIVATE_SAMPLE_FIELDS = {
    "file",
    "label",
    "label_description",
    "fault_level",
    "rul_label",
    "rul_label_description",
    "extra",
}


def _port(repository: PHMDataRepository, max_points: int = 4096) -> AgentDataPort:
    return AgentDataPort(AgentDataTools(repository, max_points))


def _registered_port(
    repository: PHMDataRepository, max_points: int = 12
) -> AgentDataPort:
    return AgentDataPort(
        AgentDataTools(repository, max_points),
        registered_streams={
            "opaque-bearing-run": [
                {
                    "source_sample_id": "1",
                    "sample_id": "opaque-acquisition-000",
                    "replay_step": 0,
                    "elapsed_minutes": 0,
                },
                {
                    "source_sample_id": "2",
                    "sample_id": "opaque-acquisition-001",
                    "replay_step": 1,
                    "elapsed_minutes": 2,
                },
            ]
        },
    )


def test_versioned_facade_preserves_v02_legacy_manifest(repository):
    legacy = AgentDataTools(repository).manifest()
    port = _port(repository)

    assert __version__ == PACKAGE_VERSION == "0.2.1"
    assert legacy["package_version"] == "0.2.1"
    assert legacy["tools"] == [
        "repository_summary",
        "list_datasets",
        "search_samples",
        "get_sample_metadata",
        "get_signal_window",
        "get_signal_statistics",
        "validate_sample",
    ]
    assert port.manifest() == {
        "provider": "phm-data-factory",
        "package_version": "0.2.1",
        "api_schema_version": "1.0.0",
        "capability_schema_version": "1.0.0",
        "backend_kind": "local_hdf5",
        "read_only": True,
        "capabilities": {
            "search_samples": True,
            "describe_sample": True,
            "bounded_window": True,
            "window_statistics": True,
            "stream_cursor": True,
            "modalities": ["continuous_series"],
            "timestamp_bases": ["sample_index"],
            "label_visibility_policy": "public_evaluator_private_v1",
        },
    }


def test_public_search_and_description_strip_private_target_fields(repository):
    port = _port(repository)
    result = port.search_samples({"task": "fault_diagnosis"}, limit=2)
    description = port.describe_sample(result[0]["sample_id"])

    assert len(result) == 2
    assert PRIVATE_SAMPLE_FIELDS.isdisjoint(result[0])
    assert PRIVATE_SAMPLE_FIELDS.isdisjoint(description)
    assert description["signal_available"] is True
    assert description["stored_shape"] == [12, 2]
    with pytest.raises(ValueError, match="unsupported public search fields"):
        port.search_samples({"label": 0}, limit=1)


def test_exact_window_artifact_summary_and_monotonic_stream(repository):
    port = _port(repository, max_points=5)
    artifact = port.read_window(
        {
            "sample_id": "1",
            "start": 0,
            "end": 5,
            "channels": [0],
            "max_points": 5,
        }
    )
    summary = port.summarize_window(artifact["artifact_ref"])

    assert artifact["artifact_ref"] == "artifact://window/000001"
    assert artifact["shape"] == [5, 1]
    assert artifact["step"] == 1
    assert summary["sample_count"] == 5
    assert summary["channels"][0]["count"] == 5
    with pytest.raises(KeyError, match="unknown window artifact"):
        port.summarize_window("artifact://window/missing")
    with pytest.raises(ValueError, match="exact window exceeds max_points"):
        port.read_window({"sample_id": "1", "start": 0, "end": 6, "max_points": 5})

    cursor = port.open_stream(
        {"stream_id": "1", "channels": ["ch_0"], "max_points": 5}
    )
    assert cursor.position == "0"
    first = cursor.next()
    second = cursor.next()
    final = cursor.next()
    assert first is not None and second is not None and final is not None
    assert (first["position"], second["position"], final["position"]) == (
        "5",
        "10",
        "12",
    )
    assert (first["start"], second["start"], final["start"]) == (0, 5, 10)
    assert first["cursor_id"] == second["cursor_id"] == final["cursor_id"]
    assert final["exhausted"] is True
    assert cursor.next() is None
    assert port.summarize_window(first["artifact_ref"])["sample_count"] == 5

    cursor.close()
    resumed = port.open_stream(
        {
            "stream_id": "1",
            "channels": ["ch_0"],
            "max_points": 5,
            "watermark": first["position"],
        }
    )
    resumed_chunk = resumed.next()
    assert resumed_chunk is not None
    assert (resumed_chunk["start"], resumed_chunk["position"]) == (5, "10")
    resumed.close()
    with pytest.raises(ValueError, match="stream cursor is closed"):
        resumed.next()


def test_port_close_is_idempotent_and_terminal(repository):
    port = _port(repository, max_points=5)
    artifact = port.read_window(
        {
            "sample_id": "1",
            "start": 0,
            "end": 5,
            "channels": [0],
            "max_points": 5,
        }
    )
    cursor = port.open_stream(
        {"stream_id": "1", "channels": [0], "max_points": 5}
    )

    port.close()
    port.close()

    with pytest.raises(ValueError, match="stream cursor is closed"):
        cursor.next()
    closed_operations = (
        port.manifest,
        lambda: port.search_samples({}, limit=1),
        lambda: port.describe_sample("1"),
        lambda: port.read_window(
            {
                "sample_id": "1",
                "start": 0,
                "end": 5,
                "channels": [0],
                "max_points": 5,
            }
        ),
        lambda: port.summarize_window(artifact["artifact_ref"]),
        lambda: port.open_stream(
            {"stream_id": "1", "channels": [0], "max_points": 5}
        ),
    )
    for operation in closed_operations:
        with pytest.raises(ValueError, match="data port is closed"):
            operation()


def test_exact_window_rejects_short_provider_rows_without_advancing_state(
    repository, monkeypatch
):
    port = _port(repository, max_points=5)
    original = port._tools.get_signal_window

    def short_window(*args, **kwargs):
        result = original(*args, **kwargs)
        result["values"] = result["values"][:-1]
        result["shape"] = [len(result["values"]), len(result["channels"])]
        return result

    monkeypatch.setattr(port._tools, "get_signal_window", short_window)

    request = {
        "sample_id": "1",
        "start": 0,
        "end": 5,
        "channels": [0],
        "max_points": 5,
    }
    with pytest.raises(ValueError, match="exact requested window"):
        port.read_window(request)

    cursor = port.open_stream(
        {"stream_id": "1", "channels": [0], "max_points": 5}
    )
    with pytest.raises(ValueError, match="exact requested window"):
        cursor.next()
    assert cursor.position == "0"

    monkeypatch.setattr(port._tools, "get_signal_window", original)
    artifact = port.read_window(request)
    assert artifact["artifact_ref"] == "artifact://window/000001"
    first = cursor.next()
    assert first is not None
    assert first["position"] == "5"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda result: result.update(shape=[5, 2]),
        lambda result: result.update(channels=[1]),
        lambda result: result["values"].__setitem__(0, [0.0, 1.0]),
    ],
)
def test_exact_window_rejects_channel_shape_or_value_width_drift(
    repository, monkeypatch, mutation
):
    port = _port(repository, max_points=5)
    original = port._tools.get_signal_window

    def drifted_window(*args, **kwargs):
        result = original(*args, **kwargs)
        mutation(result)
        return result

    monkeypatch.setattr(port._tools, "get_signal_window", drifted_window)

    with pytest.raises(ValueError, match="exact requested window"):
        port.read_window(
            {
                "sample_id": "1",
                "start": 0,
                "end": 5,
                "channels": [0],
                "max_points": 5,
            }
        )


@pytest.mark.parametrize(
    "watermark",
    [True, False, 1.0, 1.9, "1.0", " 1", "+1", "01", "-0", ""],
)
def test_stream_watermark_rejects_lossy_or_noncanonical_positions(
    repository, watermark
):
    port = _port(repository, max_points=5)

    with pytest.raises(ValueError, match="canonical integer position"):
        port.open_stream(
            {
                "stream_id": "1",
                "channels": [0],
                "max_points": 5,
                "watermark": watermark,
            }
        )


def test_registered_stream_is_opaque_and_releases_full_records_in_order(repository):
    port = _registered_port(repository)

    assert port.search_samples({}, limit=10) == []
    with pytest.raises(ValueError, match="raw source sample ids"):
        port.describe_sample("1")
    with pytest.raises(ValueError, match="raw source sample ids"):
        port.read_window({"sample_id": "2", "start": 0, "end": 8})
    with pytest.raises(ValueError, match="not yet released"):
        port.describe_sample("opaque-acquisition-001")
    with pytest.raises(ValueError, match="not yet released"):
        port.read_window(
            {"sample_id": "opaque-acquisition-001", "start": 0, "end": 8}
        )

    cursor = port.open_stream(
        {
            "stream_id": "opaque-bearing-run",
            "channels": [0],
            "max_points": 12,
        }
    )
    with pytest.raises(ValueError, match="ahead of the released position"):
        port.open_stream(
            {
                "stream_id": "opaque-bearing-run",
                "channels": [0],
                "max_points": 12,
                "watermark": "1",
            }
        )

    first = cursor.next()
    assert first is not None
    assert first["sample_id"] == "opaque-acquisition-000"
    assert first["stream_id"] == "opaque-bearing-run"
    assert (first["replay_step"], first["elapsed_minutes"]) == (0, 0)
    assert first["elapsed_delta_minutes"] == 0
    assert (first["start"], first["end"], first["shape"]) == (0, 12, [12, 1])
    assert (first["position"], first["exhausted"]) == ("1", False)
    assert "source_sample_id" not in first
    assert set(first) == {
        "artifact_ref",
        "channels",
        "cursor_id",
        "dtype",
        "elapsed_delta_minutes",
        "elapsed_minutes",
        "end",
        "end_seconds",
        "exhausted",
        "kind",
        "modality",
        "position",
        "replay_step",
        "sample_id",
        "sample_rate",
        "shape",
        "start",
        "start_seconds",
        "step",
        "stream_id",
        "time_basis",
        "values",
    }

    released = port.search_samples({}, limit=10)
    assert [row["sample_id"] for row in released] == ["opaque-acquisition-000"]
    assert PRIVATE_SAMPLE_FIELDS.isdisjoint(released[0])
    assert port.describe_sample("opaque-acquisition-000")["sample_id"] == (
        "opaque-acquisition-000"
    )
    with pytest.raises(ValueError, match="not yet released"):
        port.describe_sample("opaque-acquisition-001")

    cursor.close()
    with pytest.raises(ValueError, match="stream cursor is closed"):
        cursor.next()
    resumed = port.open_stream(
        {
            "stream_id": "opaque-bearing-run",
            "channels": [0],
            "max_points": 12,
            "watermark": first["position"],
        }
    )
    second = resumed.next()
    assert second is not None
    assert second["sample_id"] == "opaque-acquisition-001"
    assert (second["replay_step"], second["elapsed_minutes"]) == (1, 2)
    assert second["elapsed_delta_minutes"] == 2
    assert (second["start"], second["end"], second["shape"]) == (0, 8, [8, 1])
    assert (second["position"], second["exhausted"]) == ("2", True)
    assert resumed.next() is None
    resumed.close()


def test_registered_stream_bounded_failure_does_not_release_future(repository):
    port = _registered_port(repository, max_points=5)
    cursor = port.open_stream(
        {
            "stream_id": "opaque-bearing-run",
            "channels": [0],
            "max_points": 5,
        }
    )

    with pytest.raises(ValueError, match="member exceeds max_points"):
        cursor.next()
    assert cursor.position == "0"
    with pytest.raises(ValueError, match="not yet released"):
        port.describe_sample("opaque-acquisition-000")
    cursor.close()


def test_registered_member_search_is_not_truncated_by_public_limit(repository):
    port = AgentDataPort(
        AgentDataTools(repository, 12),
        registered_streams={
            "opaque-run": [
                {
                    "source_sample_id": "2",
                    "sample_id": "opaque-acquisition",
                    "replay_step": 0,
                    "elapsed_minutes": 0,
                }
            ]
        },
    )
    cursor = port.open_stream(
        {"stream_id": "opaque-run", "channels": [0], "max_points": 12}
    )
    cursor.next()

    assert [row["sample_id"] for row in port.search_samples({}, limit=1)] == [
        "opaque-acquisition"
    ]
    port.close()


@pytest.mark.parametrize(
    "members, message",
    [
        (
            [
                {
                    "source_sample_id": "1",
                    "sample_id": "opaque-0",
                    "replay_step": 1,
                    "elapsed_minutes": 0,
                }
            ],
            "zero-based and contiguous",
        ),
        (
            [
                {
                    "source_sample_id": "1",
                    "sample_id": "opaque-0",
                    "replay_step": 0,
                    "elapsed_minutes": 1,
                },
                {
                    "source_sample_id": "2",
                    "sample_id": "opaque-1",
                    "replay_step": 1,
                    "elapsed_minutes": 1,
                },
            ],
            "strictly increasing",
        ),
    ],
)
def test_registered_stream_definition_fails_closed(repository, members, message):
    with pytest.raises(ValueError, match=message):
        AgentDataPort(
            AgentDataTools(repository), registered_streams={"opaque-run": members}
        )


@pytest.mark.skipif(
    not os.getenv("PHM_PADERBORN_METADATA") or not os.getenv("PHM_PADERBORN_SIGNAL"),
    reason="set PHM_PADERBORN_METADATA and PHM_PADERBORN_SIGNAL for the real local contract",
)
def test_real_local_paderborn_six_method_contract():
    metadata = Path(os.environ["PHM_PADERBORN_METADATA"])
    signal = Path(os.environ["PHM_PADERBORN_SIGNAL"])
    repository = PHMDataRepository.from_local(metadata, signal)
    with _port(repository, max_points=256) as port:
        assert port.manifest()["api_schema_version"] == "1.0.0"
        sample = port.search_samples({"name": "RM_027_PU"}, limit=1)[0]
        assert PRIVATE_SAMPLE_FIELDS.isdisjoint(sample)
        description = port.describe_sample(sample["sample_id"])
        assert PRIVATE_SAMPLE_FIELDS.isdisjoint(description)
        artifact = port.read_window(
            {
                "sample_id": sample["sample_id"],
                "start": 0,
                "end": 256,
                "channels": [2],
                "max_points": 256,
            }
        )
        assert artifact["shape"] == [256, 1]
        assert artifact["step"] == 1
        summary = port.summarize_window(artifact["artifact_ref"])
        assert summary["sample_count"] == 256
        cursor = port.open_stream(
            {"stream_id": sample["sample_id"], "channels": [2], "max_points": 128}
        )
        first = cursor.next()
        second = cursor.next()
        assert first is not None and second is not None
        assert first["start"] == 0
        assert second["start"] == first["end"]
        assert int(second["position"]) > int(first["position"])
        cursor.close()
