from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phm_data_factory import (
    AgentDataPort,
    AgentDataTools,
    DirectoryCSVSignalStore,
    PHMDataRepository,
)


VALUE_COLUMNS = ("Mod1/ai0", "Mod1/ai1", "Mod1/ai2")


def _release(tmp_path: Path, *, rows: int = 12, columns=VALUE_COLUMNS):
    root = tmp_path / "release"
    folder = root / "Data" / "Inner_Ring" / "B10" / "DNoD" / "R1" / "PA"
    folder.mkdir(parents=True)
    signal = folder / "sample.csv"
    values = np.arange(rows * len(columns), dtype=np.float64).reshape(rows, len(columns))
    pd.DataFrame(values, columns=columns).to_csv(signal, index=False)
    metadata = pd.DataFrame(
        [
            {
                "Id": "opaque-0001",
                "Dataset_id": "saarland-inner-ring-v1",
                "Name": "Saarland inner-ring",
                "File": signal.name,
                "FolderPath": "Data\\Inner_Ring\\B10\\DNoD\\R1\\PA",
                "Visiable": 1,
                "Label": 0,
                "Domain_id": 0,
                "Sample_rate": 20000,
                "Sample_lenth": rows,
                "Channel": 3,
                "Fault_Diagnosis": 1,
                "Anomaly_Detection": 0,
                "Remaining_Life": 0,
            }
        ]
    )
    metadata_path = tmp_path / "metadata.csv"
    metadata.to_csv(metadata_path, index=False)
    return metadata_path, root, values


def test_csv_directory_runs_through_repository_and_agent_data_port(tmp_path: Path):
    metadata, root, values = _release(tmp_path)
    with PHMDataRepository.from_csv_directory(
        metadata, root, value_columns=VALUE_COLUMNS
    ) as repository:
        assert isinstance(repository.signals, DirectoryCSVSignalStore)
        assert repository.summary()["signal_store"] == "DirectoryCSVSignalStore"
        assert repository.validate_sample("opaque-0001")["valid"] is True
        window = repository.get_signal_window(
            "opaque-0001", start=2, end=8, channels=[2, 0], max_points=3
        )
        np.testing.assert_array_equal(window.values, values[2:8:2][:, [2, 0]])

        port = AgentDataPort(AgentDataTools(repository))
        artifact = port.read_window(
            {
                "sample_id": "opaque-0001",
                "start": 0,
                "end": 4,
                "channels": [0, 1, 2],
                "max_points": 4,
            }
        )
        assert artifact["shape"] == [4, 3]
        assert artifact["sample_rate"] == 20000.0
        assert "File" not in artifact
        assert "FolderPath" not in artifact


def test_csv_directory_rejects_schema_and_length_drift(tmp_path: Path):
    metadata, root, _values = _release(tmp_path, rows=4, columns=("x", "y", "z"))
    with PHMDataRepository.from_csv_directory(
        metadata, root, value_columns=VALUE_COLUMNS
    ) as repository:
        with pytest.raises(ValueError, match="columns differ"):
            repository.get_signal_window("opaque-0001", 0, 1, [0], 1)

    metadata, root, _values = _release(tmp_path / "short", rows=3)
    frame = pd.read_csv(metadata)
    frame.loc[0, "Sample_lenth"] = 4
    frame.to_csv(metadata, index=False)
    with PHMDataRepository.from_csv_directory(
        metadata, root, value_columns=VALUE_COLUMNS
    ) as repository:
        validation = repository.validate_sample("opaque-0001")
        assert validation["valid"] is False
        assert validation["errors"] == [
            "CSV signal is shorter than its registered sample length"
        ]
        with pytest.raises(ValueError, match="shorter"):
            repository.get_signal_window("opaque-0001", 0, 4, [0], 4)


def test_csv_directory_rejects_path_traversal_and_nonnumeric_values(tmp_path: Path):
    metadata, root, _values = _release(tmp_path)
    frame = pd.read_csv(metadata)
    frame.loc[0, "FolderPath"] = ".."
    frame.to_csv(metadata, index=False)
    with PHMDataRepository.from_csv_directory(
        metadata, root, value_columns=VALUE_COLUMNS
    ) as repository:
        assert repository.signals.contains("opaque-0001") is False
        with pytest.raises(ValueError, match="relative path"):
            repository.get_signal_window("opaque-0001", 0, 1, [0], 1)

    metadata, root, _values = _release(tmp_path / "text")
    signal = next(root.rglob("*.csv"))
    frame = pd.read_csv(signal)
    frame[VALUE_COLUMNS[0]] = frame[VALUE_COLUMNS[0]].astype(object)
    frame.loc[0, VALUE_COLUMNS[0]] = "not-numeric"
    frame.to_csv(signal, index=False)
    with PHMDataRepository.from_csv_directory(
        metadata, root, value_columns=VALUE_COLUMNS
    ) as repository:
        with pytest.raises(ValueError, match="must be numeric"):
            repository.get_signal_window("opaque-0001", 0, 1, [0], 1)


def test_csv_directory_projects_registered_values_from_private_segments(tmp_path: Path):
    root = tmp_path / "release"
    root.mkdir()
    signal = root / "source.csv"
    source = pd.DataFrame(
        {
            "time": np.arange(10, dtype=np.float64) / 10.0,
            "acc1": np.arange(10, dtype=np.float64) + 100.0,
            "Torq1": np.arange(10, dtype=np.float64) + 200.0,
        }
    )
    source.to_csv(signal, index=False)
    metadata = pd.DataFrame(
        [
            {
                "Id": sample_id,
                "Dataset_id": "agfd-3012-v2",
                "Name": "AGFD contiguous segment",
                "File": signal.name,
                "FolderPath": "",
                "Segment_start": segment_start,
                "Visiable": 1,
                "Label": 0,
                "Domain_id": 0,
                "Sample_rate": 10,
                "Sample_lenth": 3,
                "Channel": 1,
                "Fault_Diagnosis": 0,
                "Anomaly_Detection": 1,
                "Remaining_Life": 0,
            }
            for sample_id, segment_start in (("segment-a", 0), ("segment-b", 5))
        ]
    )
    metadata_path = tmp_path / "metadata.csv"
    metadata.to_csv(metadata_path, index=False)

    with PHMDataRepository.from_csv_directory(
        metadata_path,
        root,
        value_columns=("acc1",),
        source_columns=("time", "acc1", "Torq1"),
        segment_start_field="Segment_start",
    ) as repository:
        np.testing.assert_array_equal(
            repository.read_signal("segment-a")[:, 0], source["acc1"].iloc[0:3]
        )
        np.testing.assert_array_equal(
            repository.read_signal("segment-b")[:, 0], source["acc1"].iloc[5:8]
        )
        port = AgentDataPort(AgentDataTools(repository))
        artifact = port.read_window(
            {
                "sample_id": "segment-b",
                "start": 0,
                "end": 3,
                "channels": [0],
                "max_points": 3,
            }
        )
        self_description = port.describe_sample("segment-b")
        assert artifact["shape"] == [3, 1]
        assert artifact["channels"] == [0]
        assert "File" not in self_description
        assert "FolderPath" not in self_description
        assert "Segment_start" not in self_description


def test_csv_directory_preserves_registered_public_channel_order(tmp_path: Path):
    metadata, root, values = _release(tmp_path)
    frame = pd.read_csv(metadata)
    frame.loc[0, "Channel"] = 2
    frame.to_csv(metadata, index=False)

    with PHMDataRepository.from_csv_directory(
        metadata,
        root,
        value_columns=(VALUE_COLUMNS[2], VALUE_COLUMNS[0]),
        source_columns=VALUE_COLUMNS,
    ) as repository:
        projected = repository.read_signal("opaque-0001", start=1, end=5)

    np.testing.assert_array_equal(projected, values[1:5][:, [2, 0]])


def test_csv_directory_segment_projection_fails_closed(tmp_path: Path):
    metadata, root, _values = _release(tmp_path)
    with PHMDataRepository.from_csv_directory(
        metadata,
        root,
        value_columns=(VALUE_COLUMNS[0],),
        source_columns=VALUE_COLUMNS,
        segment_start_field="Segment_start",
    ) as repository:
        with pytest.raises(ValueError, match="must provide Segment_start"):
            repository.get_signal_window("opaque-0001", 0, 1, [0], 1)

    with pytest.raises(ValueError, match="containing value_columns"):
        PHMDataRepository.from_csv_directory(
            metadata,
            root,
            value_columns=("not-registered",),
            source_columns=VALUE_COLUMNS,
        )

    frame = pd.read_csv(metadata)
    frame.loc[0, "Segment_start"] = 1.5
    frame.to_csv(metadata, index=False)
    with PHMDataRepository.from_csv_directory(
        metadata,
        root,
        value_columns=(VALUE_COLUMNS[0],),
        source_columns=VALUE_COLUMNS,
        segment_start_field="Segment_start",
    ) as repository:
        with pytest.raises(ValueError, match="Segment_start must be an integer"):
            repository.get_signal_window("opaque-0001", 0, 1, [0], 1)
