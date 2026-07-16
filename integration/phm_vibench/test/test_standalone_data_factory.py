from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pandas as pd
import pytest

from src.data_factory.standalone import (
    build_agent_data_tools,
    build_data_backend,
    build_data_repository,
)


def _fixture(tmp_path: Path) -> SimpleNamespace:
    pd.DataFrame(
        [
            {
                "Id": 1,
                "Dataset_id": 1,
                "Name": "RM_001_CWRU",
                "Visiable": 1,
                "Label": 2,
                "Sample_lenth": 4,
                "Channel": 2,
            }
        ]
    ).to_csv(tmp_path / "metadata.csv", index=False)
    with h5py.File(tmp_path / "cache.h5", "w") as handle:
        handle.create_dataset("1", data=np.ones((4, 2)))
    config = tmp_path / "phm-data.yaml"
    config.write_text(
        "backend: local\n"
        f"metadata_path: {tmp_path / 'metadata.csv'}\n"
        f"signal_path: {tmp_path / 'cache.h5'}\n",
        encoding="utf-8",
    )
    return SimpleNamespace(factory_name="phm_data", phm_data_config=str(config))


def test_bridge_uses_explicit_backend_config(tmp_path: Path):
    args_data = _fixture(tmp_path)
    with build_data_repository(args_data) as repository:
        assert repository.validate_sample(1)["valid"] is True
        assert repository.metadata_frame("phm_vibench_v1").iloc[0]["Label"] == 2
    with build_agent_data_tools(args_data) as tools:
        assert tools.get_signal_window("1")["shape"] == [4, 2]
        assert "label" not in tools.get_sample_metadata("1")


def test_backend_alias_uses_same_repository(tmp_path: Path):
    with build_data_backend(_fixture(tmp_path)) as backend:
        assert backend.read_signal(1).shape == (4, 2)


def test_bridge_rejects_silent_local_fallback():
    with pytest.raises(ValueError, match="phm_data_config"):
        build_data_repository(SimpleNamespace(factory_name="phm_data"))
