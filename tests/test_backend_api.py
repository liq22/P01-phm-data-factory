from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phm_data_factory import MetadataCatalog, PHMDataRepository, connect
from phm_data_factory.config import RepositoryConfig
from phm_data_factory.stores.base import SignalStore


class _WritableMemoryStore(SignalStore):
    availability_is_cheap = True

    def __init__(self):
        self.data = {"1": np.ones((2, 1))}

    def read(self, sample_id, start=0, end=None, channels=None, step=1):
        array = self.data[str(sample_id)]
        end = len(array) if end is None else end
        result = array[start:end:step]
        return result if channels is None else result[:, list(channels)]

    def shape(self, sample_id):
        return self.data[str(sample_id)].shape

    def contains(self, sample_id):
        return str(sample_id) in self.data

    def list_ids(self):
        return tuple(self.data)

    def write(self, sample_id, values, *, metadata=None, **kwargs):
        array = np.asarray(values, dtype=float)
        if array.ndim == 1:
            array = array[:, None]
        self.data[str(sample_id)] = array
        payload = dict(metadata or {})
        payload.update(
            sample_id=str(sample_id),
            sample_length=len(array),
            channels=array.shape[1],
        )
        return {"sample_id": str(sample_id), "metadata": payload}


def test_repository_minimal_read_write_contract_updates_catalog():
    catalog = MetadataCatalog(pd.DataFrame([{"Id": 1, "Sample_lenth": 2, "Channel": 1}]))
    repository = PHMDataRepository(catalog, _WritableMemoryStore())
    np.testing.assert_array_equal(repository.read_signal("1"), [[1.0], [1.0]])
    repository.write_sample(
        "2",
        np.arange(6).reshape(3, 2),
        metadata={"name": "generated", "digital_twin_prediction": True},
    )
    assert repository.metadata.get("2").name == "generated"
    assert repository.metadata.get("2").digital_twin_prediction is True
    assert repository.read_signal("2").shape == (3, 2)


def test_read_only_store_rejects_write(repository):
    with pytest.raises(TypeError, match="read-only"):
        repository.write_sample("3", np.zeros((2, 1)), metadata={"sample_id": "3"})


def test_connect_accepts_mapping_and_iotdb_overrides(monkeypatch):
    captured = {}

    def fake_build(config):
        captured["config"] = config
        return "repository"

    monkeypatch.setattr("phm_data_factory.stores.iotdb.bulk.build_repository", fake_build)
    result = connect(
        {"backend": "iotdb", "iotdb": {"root": "root.original"}},
        host="db.example",
        root="root.override",
    )
    assert result == "repository"
    config = captured["config"]
    assert isinstance(config, RepositoryConfig)
    assert config.iotdb["host"] == "db.example"
    assert config.iotdb["root"] == "root.override"
