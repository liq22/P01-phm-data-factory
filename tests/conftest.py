from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from phm_data_factory import PHMDataRepository


@pytest.fixture()
def local_data(tmp_path: Path):
    metadata = pd.DataFrame(
        [
            {
                "Id": 1,
                "Dataset_id": 1,
                "Name": "RM_001_CWRU",
                "File": "97.mat",
                "Visiable": 1,
                "Label": 0,
                "Fault_level": 0,
                "RUL_label": 0,
                "Domain_id": 0,
                "Sample_rate": 12000,
                "Sample_lenth": 12,
                "Channel": 2,
                "Fault_Diagnosis": 1,
                "Anomaly_Detection": 1,
                "Remaining_Life": 0,
            },
            {
                "Id": 2,
                "Dataset_id": 1,
                "Name": "RM_001_CWRU",
                "File": "98.mat",
                "Visiable": 1,
                "Label": 1,
                "Fault_level": 1,
                "RUL_label": 0,
                "Domain_id": 1,
                "Sample_rate": 12000,
                "Sample_lenth": 8,
                "Channel": 1,
                "Fault_Diagnosis": 1,
                "Anomaly_Detection": 0,
                "Remaining_Life": 0,
            },
        ]
    )
    metadata_path = tmp_path / "metadata.csv"
    metadata.to_csv(metadata_path, index=False)
    h5_path = tmp_path / "cache.h5"
    with h5py.File(h5_path, "w") as handle:
        handle.create_dataset("1", data=np.arange(24, dtype=np.float64).reshape(12, 2))
        handle.create_dataset(
            "sample_2", data=np.arange(8, dtype=np.float64).reshape(8, 1, 1)
        )
    return metadata_path, h5_path


@pytest.fixture()
def repository(local_data):
    metadata_path, h5_path = local_data
    repo = PHMDataRepository.from_local(metadata_path, h5_path)
    try:
        yield repo
    finally:
        repo.close()
