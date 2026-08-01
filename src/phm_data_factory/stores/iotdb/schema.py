"""IoTDB metadata schema + helpers.

The SCHEMA tuple is the single source of truth for which SampleMetadata fields
are persisted to IoTDB's ``.meta`` devices. ``verify_metadata.py`` reads it off
``IoTDBImporter.SCHEMA``, so adding a field here automatically extends
verification.
"""

from __future__ import annotations
import json
from typing import Any, Mapping

from ...identity import canonical_json
from ...models import SampleMetadata, clean_value

METADATA_SCHEMA_VERSION = "phm-data-factory/iotdb-metadata-v2"

# (field_name_on_SampleMetadata, IoTDB type token)
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
    ("metadata_schema_version", "TEXT"),
    ("metadata_json", "TEXT"),
)


def to_text(value: Any) -> str | None:
    """Normalize a value to a clean optional string (used for TEXT meta fields)."""
    value = clean_value(value)
    return None if value is None else str(value)


def _json_value(value: Any) -> Any:
    value = clean_value(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"Unsupported metadata JSON value: {type(value).__name__}")


def encode_metadata(record: SampleMetadata) -> str:
    payload = _json_value(record.to_dict())
    return canonical_json(payload).decode("utf-8")


def decode_metadata(value: Any) -> dict[str, Any]:
    raw = json.loads(str(value))
    if not isinstance(raw, dict):
        raise ValueError("metadata_json must decode to an object")
    extra = raw.pop("extra", {})
    if extra:
        if not isinstance(extra, dict):
            raise ValueError("metadata_json.extra must be an object")
        raw.update(extra)
    return raw
