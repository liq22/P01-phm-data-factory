"""Pin the v0.2 stable contract: connect + the 4 PHMDataRepository ops.

Uses the H5-backed ``repository`` fixture (no IoTDB needed). ``write_sample``
must raise TypeError on a read-only backend; ``read_signal`` returns the full
window with no decimation.
"""
from __future__ import annotations

import numpy as np
import pytest

from phm_data_factory import (
    AgentDataTools,
    PHMDataRepository,
    WritableSignalStore,
    connect,
)


def test_connect_accepts_mapping_and_returns_repository(local_data):
    metadata_path, h5_path = local_data
    repo = connect(
        {
            "backend": "local",
            "metadata_path": str(metadata_path),
            "signal_path": str(h5_path),
        }
    )
    try:
        assert isinstance(repo, PHMDataRepository)
        assert repo.summary()["samples"] == 2
    finally:
        repo.close()


def test_manifest_reports_api_version():
    assert AgentDataTools.manifest()["api_version"] == "0.2"


def test_read_signal_returns_full_window_without_decimation(repository):
    # sample Id=1 is (12, 2) in the fixture cache; read_signal must NOT decimate.
    values = repository.read_signal(1)
    assert isinstance(values, np.ndarray)
    assert values.shape == (12, 2)
    # single-channel selection
    one = repository.read_signal(1, channels=[0])
    assert one.shape == (12, 1)


def test_read_signal_equals_window_with_no_max_points(repository):
    full = repository.read_signal(1)
    window = repository.get_signal_window(1, max_points=None)
    np.testing.assert_array_equal(full, window.values)


def test_write_sample_raises_typeerror_on_readonly_backend(repository):
    assert not isinstance(repository.signals, WritableSignalStore)
    with pytest.raises(TypeError):
        repository.write_sample(1, np.zeros((12, 2), dtype=np.float64))


def test_get_metadata_and_search_are_in_contract(repository):
    # get_sample_metadata + search_samples are existing methods now pinned.
    meta = repository.get_sample_metadata(1)
    assert meta["sample_id"] == "1"
    rows = repository.search_samples({"name": "RM_001_CWRU"}, limit=None)
    assert len(rows) == 2
