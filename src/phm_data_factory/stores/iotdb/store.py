"""IoTDB SignalStore: DB-backed read + single-sample write.

Decoupled from a local ``metadata.xlsx``: with ``metadata=None`` (the default)
the sample catalog is lazily loaded from IoTDB's own ``.meta`` devices, so a
fresh machine can read directly from IoTDB without the source spreadsheet.
``availability_via_catalog=True`` makes ``contains`` an O(1) catalog membership
check (the catalog IS the imported set in that mode).

Reads use the iterator result-set → pre-allocated numpy (no pandas round-trip).
``write`` is the single write path; ``IoTDBImporter.import_sample`` delegates to it.
"""

from __future__ import annotations
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ...metadata import MetadataCatalog
from ...models import SampleMetadata, id_text
from ..base import SignalStore
from .config import IoTDBConfig
from .metadata import _catalog_from_session
from .paths import IoTDBPathCodec
from .schema import SCHEMA, to_text
from .session import IoTDBSession

_MAX_INT64 = 9223372036854775807


def _field_double(field) -> float:
    """Read a DOUBLE Field, tolerating nulls and accessor-name differences."""
    is_null = getattr(field, "is_null", None)
    if callable(is_null) and is_null():
        return float("nan")
    for attr in ("get_double_value", "get_float_value", "get_long_value"):
        getter = getattr(field, attr, None)
        if callable(getter):
            try:
                return float(getter())
            except Exception:
                continue
    getter = getattr(field, "get_object_value", None)
    try:
        return float(getter() if callable(getter) else field.get_value())
    except Exception:
        return float("nan")


class IoTDBSignalStore(SignalStore):
    """IoTDB backend (read + write)."""

    def __init__(
        self,
        config: IoTDBConfig,
        metadata: MetadataCatalog | None = None,
        *,
        availability_via_catalog: bool | None = None,
    ):
        self.config = config
        self.connection = IoTDBSession(config)
        self.metadata = metadata
        self._resolved = metadata is not None
        # When True, ``contains`` trusts catalog membership as the imported set
        # (true when the catalog came from IoTDB; false for an external xlsx).
        if availability_via_catalog is None:
            availability_via_catalog = metadata is None
        self.availability_via_catalog = bool(availability_via_catalog)
        self.availability_is_cheap = self.availability_via_catalog

    @classmethod
    def connect(
        cls,
        host: str = "127.0.0.1",
        port: int = 6667,
        *,
        user: str = "root",
        password: str = "root",
        root: str = "root.vibench",
        fetch_size: int = 5000,
        zone_id: str = "UTC",
        metadata: MetadataCatalog | None = None,
        **kwargs: Any,
    ) -> "IoTDBSignalStore":
        """Convenience constructor mirroring the legacy Session kwargs."""
        return cls(
            IoTDBConfig(host, port, user, password, root, fetch_size, zone_id),
            metadata,
            **kwargs,
        )

    @property
    def session(self):
        return self.connection.open()

    # ----- metadata resolution -----
    def _ensure_metadata(self) -> None:
        if self._resolved:
            return
        self._resolved = True
        try:
            self.metadata = _catalog_from_session(self.config, self.session)
        except Exception:
            self.metadata = None

    def _record_device(self, sample_id):
        self._ensure_metadata()
        if self.metadata is None:
            raise KeyError(sample_id)
        record = self.metadata.get(sample_id)
        return record, IoTDBPathCodec.signal_device(self.config, record)

    # ----- read-only SignalStore API -----
    def list_ids(self) -> Iterable[str]:
        self._ensure_metadata()
        return tuple(self.metadata.keys()) if self.metadata is not None else ()

    def contains(self, sample_id) -> bool:
        if self.availability_via_catalog:
            self._ensure_metadata()
            return self.metadata is not None and id_text(sample_id) in self.metadata
        try:
            _, device = self._record_device(sample_id)
        except KeyError:
            return False
        return bool(self.session.check_time_series_exists(f"{device}.ch_0"))

    def shape(self, sample_id) -> tuple[int, ...]:
        self._ensure_metadata()
        if self.metadata is None:
            raise KeyError(sample_id)
        record = self.metadata.get(sample_id)
        if record.sample_length is not None and record.channels is not None:
            return record.sample_length, record.channels
        # Fallback: ask the DB (rare — importer always writes length/channels).
        device = IoTDBPathCodec.signal_device(self.config, record)
        return self._count(device), self._channel_count(device)

    def read(
        self,
        sample_id,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        step: int = 1,
    ) -> np.ndarray:
        if int(step) <= 0:
            raise ValueError("step must be positive")
        _, device = self._record_device(sample_id)
        length, count = self.shape(sample_id)
        selected = (
            list(range(count)) if channels is None else [int(c) for c in channels]
        )
        if not selected or any(c < 0 or c >= count for c in selected):
            raise IndexError("Invalid channel selection")
        start = int(start)
        end = length if end is None else min(int(end), length)
        if start < 0 or end < start or start > length:
            raise ValueError("Expected 0 <= start <= end <= length")
        measurements = [f"ch_{c}" for c in selected]
        result = self.session.execute_query_statement(
            f"SELECT {', '.join(measurements)} FROM {device} "
            f"WHERE time >= {start} AND time < {end}"
        )
        try:
            capacity = end - start
            out = np.empty((capacity, len(selected)), dtype=np.float64)
            out.fill(np.nan)  # missing/null cells surface as NaN, not garbage
            i = 0
            while result.has_next() and i < capacity:
                fields = result.next().get_fields()
                for j in range(min(len(selected), len(fields))):
                    out[i, j] = _field_double(fields[j])
                i += 1
            if i < capacity:
                out = out[:i]
        finally:
            close = getattr(result, "close_operation_handle", None)
            if callable(close):
                close()
        return out if int(step) == 1 else out[:: int(step)]

    # ----- write -----
    def write(
        self,
        sample_id,
        values: np.ndarray,
        *,
        metadata: Mapping[str, Any] | SampleMetadata | None = None,
        mode: str = "error",
        sample_rate: float | None = None,
        name: str | None = None,
        sample_length: int | None = None,
        channels: int | None = None,
        base_time: int = 0,
        chunk_size: int = 10000,
        **_: Any,
    ) -> dict[str, Any]:
        """Write one signal array (+ metadata) as an aligned IoTDB device.

        ``mode``: ``"error"`` raises if the sample already exists; ``"overwrite"``
        clears the existing signal data first. Returns a report dict shaped like
        ``IoTDBImporter.import_sample`` so the bulk importer can delegate here.
        """
        if mode not in ("error", "overwrite"):
            raise ValueError("mode must be 'error' or 'overwrite'")
        if int(chunk_size) <= 0:
            raise ValueError("chunk_size must be positive")
        matrix = np.asarray(values, dtype=np.float64)
        if matrix.ndim == 1:
            matrix = matrix[:, None]
        while matrix.ndim > 2 and matrix.shape[-1] == 1:
            matrix = np.squeeze(matrix, -1)
        if matrix.ndim != 2:
            raise ValueError(f"Cannot write signal of shape {matrix.shape}")
        length, nchan = matrix.shape

        record = self._coerce_record(
            sample_id,
            metadata,
            sample_rate=sample_rate,
            name=name,
            sample_length=sample_length,
            channels=channels,
        )
        if record.sample_length is None:
            record = replace(record, sample_length=length)
        elif int(record.sample_length) != length:
            raise ValueError(
                f"metadata sample_length={record.sample_length} does not match "
                f"values length={length}"
            )
        if record.channels is None:
            record = replace(record, channels=nchan)
        elif int(record.channels) != nchan:
            raise ValueError(
                f"metadata channels={record.channels} does not match "
                f"values channels={nchan}"
            )

        device = IoTDBPathCodec.signal_device(self.config, record)
        existing = self._existing_record(sample_id)
        if mode == "error" and self._signal_exists(device):
            raise FileExistsError(
                f"Sample {sample_id} already exists at {device} "
                "(use mode='overwrite' to replace)"
            )
        if mode == "overwrite":
            drop_records = [r for r in (existing, record) if r is not None]
            seen: set[str] = set()
            for item in drop_records:
                item_device = IoTDBPathCodec.signal_device(self.config, item)
                if item_device not in seen:
                    item_channels = item.channels or nchan
                    self._drop_signal(item_device, int(item_channels))
                    seen.add(item_device)
                meta_device = IoTDBPathCodec.metadata_device(self.config, item)
                if meta_device not in seen:
                    self._drop_metadata(item)
                    seen.add(meta_device)

        self.ensure_database()
        self._ensure_signal(device, nchan)
        self._write_metadata(record)

        from ...iotdb import _imports

        _, Types, _, _, Tablet = _imports()
        measurements = [f"ch_{i}" for i in range(nchan)]
        chunks = 0
        for s in range(0, length, int(chunk_size)):
            e = min(s + int(chunk_size), length)
            tablet = Tablet(
                device,
                measurements,
                [Types.DOUBLE] * nchan,
                [np.asarray(matrix[s:e, i], dtype=np.float64) for i in range(nchan)],
                np.arange(base_time + s, base_time + e, dtype=np.int64),
            )
            self.session.insert_aligned_tablet(tablet)
            chunks += 1

        # When the catalog came from IoTDB, it's now stale (new sample missing).
        # Force a reload on next access so store-level contains/shape/read see it.
        # (Repository-level search/metadata still reflect connect-time state; re-
        # connect() to refresh them — see docs/API_CONTRACT.md.)
        if self.availability_via_catalog:
            self._resolved = False
            self.metadata = None

        return {
            "sample_id": str(sample_id),
            "device": device,
            "length": length,
            "channels": nchan,
            "chunks": chunks,
        }

    def delete(self, sample_id) -> None:
        """Admin-only (NOT in the v0.2 stable contract). Drops signal + metadata."""
        record, device = self._record_device(sample_id)
        nchan = record.channels or self._channel_count(device)
        self._drop_signal(device, nchan)
        self._drop_metadata(record)
        if self.availability_via_catalog:
            self._resolved = False
            self.metadata = None

    # ----- internals -----
    def _existing_record(self, sample_id) -> SampleMetadata | None:
        try:
            self._ensure_metadata()
            if self.metadata is not None and id_text(sample_id) in self.metadata:
                return self.metadata.get(sample_id)
        except Exception:
            return None
        return None

    def _coerce_record(
        self,
        sample_id,
        metadata,
        *,
        sample_rate,
        name,
        sample_length,
        channels,
    ) -> SampleMetadata:
        if isinstance(metadata, SampleMetadata):
            base = metadata
        elif metadata:
            base = SampleMetadata.from_mapping(
                {**dict(metadata), "sample_id": sample_id}
            )
        else:
            base = SampleMetadata(sample_id=id_text(sample_id))
        overrides: dict[str, Any] = {
            "sample_id": id_text(sample_id),
            "sample_rate": sample_rate if sample_rate is not None else base.sample_rate,
            "sample_length": (
                sample_length if sample_length is not None else base.sample_length
            ),
            "channels": channels if channels is not None else base.channels,
        }
        if name is not None:
            overrides["name"] = name
        return replace(base, **overrides)

    def ensure_database(self) -> None:
        try:
            self.session.execute_non_query_statement(
                f"CREATE DATABASE {self.config.root}"
            )
        except Exception as exc:
            if "exist" not in str(exc).lower() and "already" not in str(exc).lower():
                try:
                    self.session.set_storage_group(self.config.root)
                except Exception as fallback:
                    if (
                        "exist" not in str(fallback).lower()
                        and "already" not in str(fallback).lower()
                    ):
                        raise exc

    def _signal_exists(self, device: str) -> bool:
        return bool(self.session.check_time_series_exists(f"{device}.ch_0"))

    def _ensure_signal(self, device: str, channels: int) -> None:
        from ...iotdb import _imports

        _, Types, Enc, Comp, _ = _imports()
        names = [f"ch_{i}" for i in range(channels)]
        missing = [
            n for n in names if not self.session.check_time_series_exists(f"{device}.{n}")
        ]
        if missing:
            self.session.create_aligned_time_series(
                device,
                missing,
                [Types.DOUBLE] * len(missing),
                [Enc.GORILLA] * len(missing),
                [Comp.SNAPPY] * len(missing),
            )

    def _write_metadata(self, record: SampleMetadata) -> None:
        from ...iotdb import _imports

        _, Types, Enc, Comp, _ = _imports()
        device = IoTDBPathCodec.metadata_device(self.config, record)
        names = [n for n, _ in SCHEMA]
        types = [getattr(Types, t) for _, t in SCHEMA]
        missing = [
            i
            for i, n in enumerate(names)
            if not self.session.check_time_series_exists(f"{device}.{n}")
        ]
        if missing:
            self.session.create_aligned_time_series(
                device,
                [names[i] for i in missing],
                [types[i] for i in missing],
                [Enc.PLAIN] * len(missing),
                [Comp.SNAPPY] * len(missing),
            )
        values = {
            "sample_id": record.sample_id,
            "dataset_id": to_text(record.dataset_id),
            "name": record.name,
            "file": record.file,
            "visible": record.visible,
            "label": to_text(record.label),
            "fault_level": to_text(record.fault_level),
            "rul_label": to_text(record.rul_label),
            "domain_id": to_text(record.domain_id),
            "sample_rate": record.sample_rate,
            "sample_length": record.sample_length,
            "channels": record.channels,
            "fault_diagnosis": record.fault_diagnosis,
            "anomaly_detection": record.anomaly_detection,
            "remaining_life": record.remaining_life,
            "digital_twin_prediction": record.digital_twin_prediction,
        }
        chosen = [
            (n, t, values[n]) for n, t in zip(names, types) if values.get(n) is not None
        ]
        self.session.insert_aligned_record(
            device,
            0,
            [x[0] for x in chosen],
            [x[1] for x in chosen],
            [x[2] for x in chosen],
        )

    def _drop_signal(self, device: str, channels: int) -> None:
        paths = [f"{device}.ch_{i}" for i in range(channels)]
        self._drop_paths(paths)

    def _drop_metadata(self, record: SampleMetadata) -> None:
        device = IoTDBPathCodec.metadata_device(self.config, record)
        self._drop_paths([f"{device}.{name}" for name, _ in SCHEMA])

    def _drop_paths(self, paths: list[str]) -> None:
        try:
            self.session.delete_data_in_range(paths, 0, _MAX_INT64)
        except Exception:
            try:
                self.session.delete_time_series(paths)
            except Exception:
                pass  # best-effort; re-insert upserts over existing timestamps

    def _count(self, device: str) -> int:
        result = self.session.execute_query_statement(
            f"SELECT COUNT(ch_0) FROM {device}"
        )
        try:
            frame = result.todf()
        finally:
            close = getattr(result, "close_operation_handle", None)
            if callable(close):
                close()
        try:
            return int(frame.iloc[0, 0])
        except Exception:
            return 0

    def _channel_count(self, device: str) -> int:
        count = 0
        while self.session.check_time_series_exists(f"{device}.ch_{count}"):
            count += 1
        return count or 1

    def close(self) -> None:
        self.connection.close()
