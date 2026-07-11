"""Load a MetadataCatalog from IoTDB's ``.meta`` devices.

``_catalog_from_session`` is the core loader and takes a caller-provided session
(so the IoTDB store can lazy-load through its own injectable session).
``load_metadata_from_iotdb`` opens its own session for standalone use.
"""

from __future__ import annotations
import re

from ...metadata import MetadataCatalog
from .config import IoTDBConfig
from .session import IoTDBSession


def _catalog_from_session(config: IoTDBConfig, session) -> MetadataCatalog | None:
    """Build a MetadataCatalog from the ``.meta`` devices. Returns None if empty."""
    result = session.execute_query_statement(
        f"SELECT * FROM {config.root}.**.meta ALIGN BY DEVICE"
    )
    try:
        frame = result.todf()
    finally:
        close = getattr(result, "close_operation_handle", None)
        if callable(close):
            close()
    if frame is None or frame.empty:
        return None
    rename = {}
    for col in frame.columns:
        name = str(col)
        rename[col] = (
            name.lower()
            if name.lower() in {"time", "device"}
            else name.rsplit(".", 1)[-1]
        )
    frame = frame.rename(columns=rename)
    if "sample_id" not in frame and "device" in frame:
        frame["sample_id"] = frame["device"].map(
            lambda x: (re.search(r"\.sample_([^\.]+)\.meta$", str(x)) or [None, None])[
                1
            ]
        )
    frame = frame.drop(columns=[c for c in ("time", "device") if c in frame]).dropna(
        subset=["sample_id"]
    )
    if frame.empty:
        return None
    return MetadataCatalog(frame, "sample_id")


def load_metadata_from_iotdb(config: IoTDBConfig) -> MetadataCatalog:
    with IoTDBSession(config) as session:
        catalog = _catalog_from_session(config, session)
    if catalog is None:
        raise ValueError(f"No metadata below {config.root}")
    return catalog
