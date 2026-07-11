"""Typed PHM domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def id_text(value: Any) -> str:
    value = clean_value(value)
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def as_bool(value: Any) -> bool | None:
    value = clean_value(value)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _int(value: Any) -> int | None:
    value = clean_value(value)
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    value = clean_value(value)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _lookup(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row:
            return row[name]
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(value: Any) -> str | None:
    value = clean_value(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class SampleMetadata:
    sample_id: str
    dataset_id: Any = None
    name: str | None = None
    description: str | None = None
    sample_type: str | None = None
    file: str | None = None
    visible: bool | None = None
    label: Any = None
    label_description: str | None = None
    fault_level: Any = None
    rul_label: Any = None
    rul_label_description: str | None = None
    domain_id: Any = None
    domain_description: str | None = None
    sample_rate: float | None = None
    sample_length: int | None = None
    channels: int | None = None
    fault_diagnosis: bool | None = None
    anomaly_detection: bool | None = None
    remaining_life: bool | None = None
    digital_twin_prediction: bool | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "SampleMetadata":
        clean = {str(k): clean_value(v) for k, v in row.items()}
        sample_id = _lookup(clean, "Id", "id", "sample_id")
        if sample_id is None:
            raise ValueError("Metadata row must contain Id")
        known = {
            x.lower()
            for x in (
                "Id",
                "sample_id",
                "Dataset_id",
                "Name",
                "Description",
                "TYPE",
                "File",
                "Visiable",
                "Visible",
                "Label",
                "Label_Description",
                "Fault_level",
                "RUL_label",
                "RUL_label_description",
                "Domain_id",
                "Domain_description",
                "Sample_rate",
                "Sample_lenth",
                "Sample_length",
                "Channel",
                "Channels",
                "Fault_Diagnosis",
                "Anomaly_Detection",
                "Remaining_Life",
                "Digital_Twin_Prediction",
            )
        }
        return cls(
            sample_id=id_text(sample_id),
            dataset_id=_lookup(clean, "Dataset_id", "dataset_id"),
            name=_text(_lookup(clean, "Name", "name")),
            description=_text(_lookup(clean, "Description", "description")),
            sample_type=_text(_lookup(clean, "TYPE", "type")),
            file=_text(_lookup(clean, "File", "file")),
            visible=as_bool(_lookup(clean, "Visiable", "Visible", "visible")),
            label=_lookup(clean, "Label", "label"),
            label_description=_text(
                _lookup(clean, "Label_Description", "label_description")
            ),
            fault_level=_lookup(clean, "Fault_level", "fault_level"),
            rul_label=_lookup(clean, "RUL_label", "rul_label"),
            rul_label_description=_text(
                _lookup(clean, "RUL_label_description", "rul_label_description")
            ),
            domain_id=_lookup(clean, "Domain_id", "domain_id"),
            domain_description=_text(
                _lookup(clean, "Domain_description", "domain_description")
            ),
            sample_rate=_float(_lookup(clean, "Sample_rate", "sample_rate")),
            sample_length=_int(
                _lookup(clean, "Sample_lenth", "Sample_length", "sample_length")
            ),
            channels=_int(_lookup(clean, "Channel", "Channels", "channels")),
            fault_diagnosis=as_bool(
                _lookup(clean, "Fault_Diagnosis", "fault_diagnosis")
            ),
            anomaly_detection=as_bool(
                _lookup(clean, "Anomaly_Detection", "anomaly_detection")
            ),
            remaining_life=as_bool(_lookup(clean, "Remaining_Life", "remaining_life")),
            digital_twin_prediction=as_bool(
                _lookup(clean, "Digital_Twin_Prediction", "digital_twin_prediction")
            ),
            extra={k: v for k, v in clean.items() if k.lower() not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "dataset_id": clean_value(self.dataset_id),
            "name": self.name,
            "description": self.description,
            "type": self.sample_type,
            "file": self.file,
            "visible": self.visible,
            "label": clean_value(self.label),
            "label_description": self.label_description,
            "fault_level": clean_value(self.fault_level),
            "rul_label": clean_value(self.rul_label),
            "rul_label_description": self.rul_label_description,
            "domain_id": clean_value(self.domain_id),
            "domain_description": self.domain_description,
            "sample_rate": self.sample_rate,
            "sample_length": self.sample_length,
            "channels": self.channels,
            "fault_diagnosis": self.fault_diagnosis,
            "anomaly_detection": self.anomaly_detection,
            "remaining_life": self.remaining_life,
            "digital_twin_prediction": self.digital_twin_prediction,
            "extra": {k: clean_value(v) for k, v in self.extra.items()},
        }


@dataclass(frozen=True)
class SignalWindow:
    sample_id: str
    start: int
    end: int
    step: int
    channels: tuple[int, ...]
    sample_rate: float | None
    values: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        result = {
            "sample_id": self.sample_id,
            "start": self.start,
            "end": self.end,
            "step": self.step,
            "channels": list(self.channels),
            "sample_rate": self.sample_rate,
            "shape": list(self.values.shape),
            "time_basis": "sample_index",
            "values": self.values.tolist(),
        }
        if self.sample_rate:
            result["start_seconds"] = self.start / self.sample_rate
            result["end_seconds"] = self.end / self.sample_rate
        return result
