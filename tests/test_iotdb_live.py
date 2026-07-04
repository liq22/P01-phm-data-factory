from __future__ import annotations

import os

import pytest

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
