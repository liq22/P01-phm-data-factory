from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from phm_data_factory import PHMDataRepository


def test_directory_store_resolves_dataset_h5(tmp_path: Path):
    metadata = tmp_path / "metadata.csv"
    pd.DataFrame(
        [{"Id": 7, "Name": "RM_001_CWRU", "Sample_lenth": 4, "Channel": 2}]
    ).to_csv(metadata, index=False)
    with h5py.File(tmp_path / "RM_001_CWRU.h5", "w") as handle:
        handle.create_dataset("Id_7", data=np.ones((4, 2)))

    with PHMDataRepository.from_local(metadata, tmp_path) as repository:
        assert repository.validate_sample(7)["valid"] is True
        assert tuple(repository.get_signal_window(7, max_points=None).values.shape) == (
            4,
            2,
        )
