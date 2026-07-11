"""IoTDB metadata schema + helpers.

The SCHEMA tuple is the single source of truth for which SampleMetadata fields
are persisted to IoTDB's ``.meta`` devices. ``verify_metadata.py`` reads it off
``IoTDBImporter.SCHEMA``, so adding a field here automatically extends
verification.
"""

from __future__ import annotations
from typing import Any

from ...models import clean_value

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
)


def to_text(value: Any) -> str | None:
    """Normalize a value to a clean optional string (used for TEXT meta fields)."""
    value = clean_value(value)
    return None if value is None else str(value)
