from __future__ import annotations

import numpy as np
import pytest

from phm_data_factory import AgentDataTools, MetadataAccessor, MetadataCatalog


def test_metadata_catalog_and_structured_search(local_data):
    metadata_path, _ = local_data
    catalog = MetadataCatalog.from_file(metadata_path)
    assert catalog.get(1.0).sample_id == "1"
    assert catalog.get("1").sample_rate == 12000
    results = catalog.search({"fault_diagnosis": True, "domain_id": 0})
    assert [record.sample_id for record in results] == ["1"]
    assert catalog.summary()["tasks"]["anomaly_detection"] == 1
    assert catalog.list_datasets() == [
        {"dataset_id": 1, "name": "RM_001_CWRU", "samples": 2}
    ]
    with pytest.raises(ValueError):
        catalog.search(limit=-1)


def test_metadata_accessor_compatibility(local_data):
    metadata_path, _ = local_data
    accessor = MetadataAccessor.from_file(metadata_path)
    assert accessor[1]["File"] == "97.mat"
    assert accessor.get(999, {"missing": True}) == {"missing": True}
    assert list(accessor.df["Id"]) == [1, 2]


def test_repository_window_is_bounded_and_canonical(repository):
    window = repository.get_signal_window(1, start=0, end=12, max_points=5)
    assert window.step == 3
    assert tuple(window.values.shape) == (4, 2)
    np.testing.assert_array_equal(window.values[:, 0], [0, 6, 12, 18])

    trailing_singleton = repository.get_signal_window(2, max_points=None)
    assert tuple(trailing_singleton.values.shape) == (8, 1)
    with pytest.raises(ValueError):
        repository.get_signal_window(1, max_points=0)


def test_repository_statistics_validation_and_summary(repository):
    stats = repository.get_signal_statistics(1, channels=[1], max_points=100)
    assert stats["channels"][0]["channel"] == 1
    assert stats["channels"][0]["count"] == 12
    assert repository.validate_sample(1)["valid"] is True
    validation = repository.validate_sample(2)
    assert validation["valid"] is True
    assert validation["warnings"]
    summary = repository.summary()
    assert summary["signals_available"] == 2
    assert summary["availability_checked"] is True


def test_agent_tools_have_bounded_json_surface(repository):
    tools = AgentDataTools(repository, default_max_points=3)
    result = tools.get_signal_window("1")
    assert result["shape"] == [3, 2]
    assert len(result["values"]) == 3
    assert tools.search_samples(task="fault", limit=5)[0]["sample_id"] == "1"
    assert "get_signal_window" in tools.manifest()["tools"]
