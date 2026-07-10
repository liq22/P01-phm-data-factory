from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pandas as pd

from src.data_factory.standalone import build_agent_data_tools, build_data_repository


def _write_data(root: Path) -> None:
    pd.DataFrame(
        [{"Id": 1, "Name": "RM_001_CWRU", "Sample_lenth": 4, "Channel": 2}]
    ).to_csv(root / "metadata.csv", index=False)
    with h5py.File(root / "cache.h5", "w") as handle:
        handle.create_dataset("1", data=np.ones((4, 2)))


def test_standalone_bridge_uses_existing_data_config(tmp_path: Path):
    _write_data(tmp_path)
    args_data = SimpleNamespace(
        data_dir=str(tmp_path),
        metadata_file="metadata.csv",
        agent_max_points=2,
    )
    with build_data_repository(args_data) as repository:
        assert repository.validate_sample(1)["valid"] is True
    with build_agent_data_tools(args_data) as tools:
        assert tools.get_signal_window("1")["shape"] == [2, 2]


def test_standalone_bridge_can_select_unified_backend_config(tmp_path: Path):
    _write_data(tmp_path)
    (tmp_path / "phm-data.yaml").write_text(
        "backend: local\n"
        "metadata_path: metadata.csv\n"
        "signal_path: cache.h5\n",
        encoding="utf-8",
    )
    args_data = SimpleNamespace(
        data_dir=str(tmp_path),
        phm_data_config="phm-data.yaml",
        agent_max_points=2,
    )
    with build_data_repository(args_data) as repository:
        assert repository.read_signal("1").shape == (4, 2)
    with build_agent_data_tools(args_data) as tools:
        assert tools.get_signal_window("1")["shape"] == [2, 2]
