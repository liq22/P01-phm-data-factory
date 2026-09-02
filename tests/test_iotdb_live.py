from __future__ import annotations

import json
import os
import time

import pytest

from phm_data_factory import AgentDataPort, AgentDataTools
from phm_data_factory.config import RepositoryConfig, build_repository
from phm_data_factory.iotdb import IoTDBConfig, IoTDBSession


def _live_config() -> IoTDBConfig:
    return IoTDBConfig(
        host=os.getenv("IOTDB_HOST", "127.0.0.1"),
        port=int(os.getenv("IOTDB_PORT", "6667")),
        user=os.getenv("IOTDB_USER", "root"),
        password=os.getenv("IOTDB_PASSWORD", "root"),
        root=os.getenv("IOTDB_ROOT", "root.vibench"),
        fetch_size=int(os.getenv("IOTDB_FETCH_SIZE", "5000")),
        zone_id=os.getenv("IOTDB_ZONE_ID", "UTC"),
    )


@pytest.mark.skipif(
    os.getenv("PHM_IOTDB_LIVE") != "1",
    reason="set PHM_IOTDB_LIVE=1 to run against a live IoTDB with imported PHM data",
)
def test_live_iotdb_has_readable_phm_data():
    db = _live_config()
    with IoTDBSession(db):
        pass

    config = RepositoryConfig.from_mapping(
        {
            "backend": "iotdb",
            "iotdb": {
                "host": db.host,
                "port": db.port,
                "user": db.user,
                "password": db.password,
                "root": db.root,
                "fetch_size": db.fetch_size,
                "zone_id": db.zone_id,
            },
        }
    )
    with build_repository(config) as repo:
        summary = repo.summary()
        assert summary["samples"] > 0
        sample_id = repo.metadata.keys()[0]
        metadata = repo.get_sample_metadata(sample_id)
        assert metadata["sample_id"] == sample_id
        end = min(int(metadata.get("sample_length") or 1024), 1024)
        window = repo.get_signal_window(sample_id, start=0, end=end, max_points=128)
        assert window.values.size > 0
        assert window.step >= 1


@pytest.mark.skipif(
    os.getenv("PHM_IOTDB_LIVE") != "1",
    reason="set PHM_IOTDB_LIVE=1 to run against a live IoTDB with imported PHM data",
)
def test_live_iotdb_six_method_data_port_contract(record_property):
    db = _live_config()
    latency_ms: dict[str, float] = {}

    started = time.perf_counter_ns()
    with IoTDBSession(db):
        pass
    latency_ms["connect"] = (time.perf_counter_ns() - started) / 1_000_000

    config = RepositoryConfig.from_mapping(
        {
            "backend": "iotdb",
            "iotdb": {
                "host": db.host,
                "port": db.port,
                "user": db.user,
                "password": db.password,
                "root": db.root,
                "fetch_size": db.fetch_size,
                "zone_id": db.zone_id,
            },
        }
    )

    started = time.perf_counter_ns()
    repository = build_repository(config)
    latency_ms["repository_open"] = (
        time.perf_counter_ns() - started
    ) / 1_000_000
    with AgentDataPort(AgentDataTools(repository, 128)) as port:
        started = time.perf_counter_ns()
        manifest = port.manifest()
        latency_ms["manifest"] = (time.perf_counter_ns() - started) / 1_000_000
        assert manifest["backend_kind"] == "iotdb"

        started = time.perf_counter_ns()
        samples = port.search_samples({}, limit=1)
        latency_ms["search"] = (time.perf_counter_ns() - started) / 1_000_000
        assert samples
        sample = samples[0]

        started = time.perf_counter_ns()
        description = port.describe_sample(sample["sample_id"])
        latency_ms["describe"] = (time.perf_counter_ns() - started) / 1_000_000
        sample_length = int(description["sample_length"])
        assert sample_length >= 3
        end = min(sample_length, 128)

        started = time.perf_counter_ns()
        artifact = port.read_window(
            {
                "sample_id": sample["sample_id"],
                "start": 0,
                "end": end,
                "channels": [0],
                "max_points": 128,
            }
        )
        latency_ms["exact_read_window"] = (
            time.perf_counter_ns() - started
        ) / 1_000_000
        assert (artifact["start"], artifact["end"], artifact["step"]) == (0, end, 1)

        started = time.perf_counter_ns()
        summary = port.summarize_window(artifact["artifact_ref"])
        latency_ms["summarize"] = (time.perf_counter_ns() - started) / 1_000_000
        assert summary["sample_count"] == end

        stream_points = max(1, min(32, sample_length // 3))
        started = time.perf_counter_ns()
        cursor = port.open_stream(
            {
                "stream_id": sample["sample_id"],
                "channels": [0],
                "max_points": stream_points,
            }
        )
        latency_ms["open_stream"] = (time.perf_counter_ns() - started) / 1_000_000

        chunks = []
        try:
            for index in range(3):
                started = time.perf_counter_ns()
                chunk = cursor.next()
                latency_ms[f"stream_next_{index + 1}"] = (
                    time.perf_counter_ns() - started
                ) / 1_000_000
                assert chunk is not None
                chunks.append(chunk)
        finally:
            started = time.perf_counter_ns()
            cursor.close()
            latency_ms["stream_close"] = (
                time.perf_counter_ns() - started
            ) / 1_000_000

        assert chunks[0]["start"] == 0
        assert chunks[1]["start"] == chunks[0]["end"]
        assert chunks[2]["start"] == chunks[1]["end"]
        assert [int(chunk["position"]) for chunk in chunks] == sorted(
            {int(chunk["position"]) for chunk in chunks}
        )
        with pytest.raises(ValueError, match="stream cursor is closed"):
            cursor.next()

        latency_payload = json.dumps(latency_ms, sort_keys=True)
        record_property("w2_iotdb_latency_ms", latency_payload)
        print(json.dumps({"w2_iotdb_latency_ms": latency_ms}, sort_keys=True))
