"""IoTDB metadata schema and value normalization."""

from __future__ import annotations

from typing import Any

from ...models import SampleMetadata, clean_value

SCHEMA = (
    ("sample_id", "TEXT"),
    ("dataset_id", "TEXT"),
    ("name", "TEXT"),
    ("file", "TEXT"),
    ("visible", "BOOLEAN"),
    ("label", "TEXT"),
    ("fault_level", "TEXT"),
    ("rul_label", "TEXT"),
    ("domain_id", "TEXT"),
    ("sample_rate", "DOUBLE"),
    ("sample_length", "INT64"),
    ("channels", "INT32"),
    ("fault_diagnosis", "BOOLEAN"),
    ("anomaly_detection", "BOOLEAN"),
    ("remaining_life", "BOOLEAN"),
    ("digital_twin_prediction", "BOOLEAN"),
)


def _txt(value: Any) -> str | None:
    value = clean_value(value)
    return None if value is None else str(value)


def metadata_values(record: SampleMetadata) -> dict[str, Any]:
    return {
        "sample_id": record.sample_id,
        "dataset_id": _txt(record.dataset_id),
        "name": record.name,
        "file": record.file,
        "visible": record.visible,
        "label": _txt(record.label),
        "fault_level": _txt(record.fault_level),
        "rul_label": _txt(record.rul_label),
        "domain_id": _txt(record.domain_id),
        "sample_rate": record.sample_rate,
        "sample_length": record.sample_length,
        "channels": record.channels,
        "fault_diagnosis": record.fault_diagnosis,
        "anomaly_detection": record.anomaly_detection,
        "remaining_life": record.remaining_life,
        "digital_twin_prediction": record.digital_twin_prediction,
    }
