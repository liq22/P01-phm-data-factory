"""IoTDB-backed metadata loading and sample index."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ...metadata import MetadataCatalog
from ...models import SampleMetadata, clean_value, id_text
from .paths import IoTDBPathCodec
from .session import IoTDBSession


def _close_result(result: Any) -> None:
    close = getattr(result, "close_operation_handle", None)
    if callable(close):
        close()


def _normalize_metadata_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for column in frame.columns:
        name = str(column)
        lowered = name.lower()
        rename[column] = (
            lowered if lowered in {"time", "device"} else name.rsplit(".", 1)[-1]
        )
    normalized = frame.rename(columns=rename).copy()
    if "sample_id" not in normalized and "device" in normalized:
        normalized["sample_id"] = normalized["device"].map(
            IoTDBPathCodec.sample_id_from_device
        )
    if "sample_id" in normalized:
        normalized["sample_id"] = normalized["sample_id"].map(id_text)
    return normalized


def query_metadata_frame(config, session=None) -> pd.DataFrame:
    connection = None
    if session is None:
        connection = IoTDBSession(config)
        session = connection.open()
    try:
        result = session.execute_query_statement(
            f"SELECT * FROM {config.root}.**.meta ALIGN BY DEVICE"
        )
        try:
            frame = result.todf()
        finally:
            _close_result(result)
    finally:
        if connection is not None:
            connection.close()
    return _normalize_metadata_frame(frame)


def _catalog_from_frame(frame: pd.DataFrame, root: str) -> MetadataCatalog:
    if frame.empty:
        raise ValueError(f"No metadata below {root}")
    catalog_frame = frame.drop(
        columns=[column for column in ("time", "device") if column in frame]
    ).dropna(subset=["sample_id"])
    return MetadataCatalog(catalog_frame, "sample_id")


@dataclass(frozen=True)
class _SampleRef:
    record: SampleMetadata
    signal_device: str


class _SampleIndex:
    """One-query, in-memory index of committed IoTDB samples."""

    def __init__(self, entries: dict[str, _SampleRef] | None = None):
        self.entries = entries or {}

    @classmethod
    def from_frame(cls, config, frame: pd.DataFrame) -> "_SampleIndex":
        entries: dict[str, _SampleRef] = {}
        for _, row in frame.iterrows():
            raw = {str(key): clean_value(value) for key, value in row.to_dict().items()}
            sample_id = id_text(raw.get("sample_id"))
            if not sample_id:
                continue
            raw["sample_id"] = sample_id
            try:
                record = SampleMetadata.from_mapping(raw)
            except ValueError:
                continue
            device = raw.get("device")
            signal_device = (
                IoTDBPathCodec.signal_from_metadata_device(str(device))
                if device
                else IoTDBPathCodec.signal_device(config, record)
            )
            previous = entries.get(sample_id)
            if previous is not None and previous.signal_device != signal_device:
                raise ValueError(
                    f"Duplicate sample_id {sample_id} in {previous.signal_device} and {signal_device}"
                )
            entries[sample_id] = _SampleRef(record, signal_device)
        return cls(entries)

    @classmethod
    def build(cls, config, session) -> "_SampleIndex":
        return cls.from_frame(config, query_metadata_frame(config, session=session))

    def __contains__(self, sample_id: object) -> bool:
        return id_text(sample_id) in self.entries

    def __getitem__(self, sample_id: str | int) -> _SampleRef:
        return self.entries[id_text(sample_id)]

    def keys(self):
        return tuple(self.entries.keys())


def load_metadata_and_index(config) -> tuple[MetadataCatalog, _SampleIndex]:
    """Load repository metadata and the signal-device index with one query."""
    frame = query_metadata_frame(config)
    return _catalog_from_frame(frame, config.root), _SampleIndex.from_frame(config, frame)


def load_metadata_from_iotdb(config) -> MetadataCatalog:
    return load_metadata_and_index(config)[0]
