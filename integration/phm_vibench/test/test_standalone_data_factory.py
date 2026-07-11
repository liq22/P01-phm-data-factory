from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pandas as pd

from src.data_factory.standalone import (
    build_agent_data_tools,
    build_data_backend,
    build_data_repository,
)


def test_standalone_bridge_uses_existing_data_config(tmp_path: Path):
    pd.DataFrame(
        [{"Id": 1, "Name": "RM_001_CWRU", "Sample_lenth": 4, "Channel": 2}]
    ).to_csv(tmp_path / "metadata.csv", index=False)
    with h5py.File(tmp_path / "cache.h5", "w") as handle:
        handle.create_dataset("1", data=np.ones((4, 2)))

    args_data = SimpleNamespace(
        data_dir=str(tmp_path),
        metadata_file="metadata.csv",
        agent_max_points=2,
    )
    with build_data_repository(args_data) as repository:
        assert repository.validate_sample(1)["valid"] is True
    with build_agent_data_tools(args_data) as tools:
        assert tools.get_signal_window("1")["shape"] == [2, 2]


def test_build_data_backend_local_fallback(tmp_path: Path):
    """Without phm_data_config, build_data_backend returns a local repository
    exposing the v0.2 contract (read_signal)."""
    pd.DataFrame(
        [{"Id": 1, "Name": "RM_001_CWRU", "Sample_lenth": 4, "Channel": 2}]
    ).to_csv(tmp_path / "metadata.csv", index=False)
    with h5py.File(tmp_path / "cache.h5", "w") as handle:
        handle.create_dataset("1", data=np.ones((4, 2)))

    args_data = SimpleNamespace(
        data_dir=str(tmp_path), metadata_file="metadata.csv"
    )
    with build_data_backend(args_data) as backend:
        # v0.2 contract ops
        assert backend.get_sample_metadata(1)["sample_id"] == "1"
        assert backend.read_signal(1).shape == (4, 2)
        assert backend.search_samples(limit=None)
