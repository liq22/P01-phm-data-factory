"""Read/write IoTDB SignalStore implementation."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Mapping, Sequence

import numpy as np

from ...metadata import MetadataCatalog
from ...models import SampleMetadata, id_text
from ..base import SignalStore, WritableSignalStore
from .config import IoTDBConfig
from .metadata import _SampleIndex, _close_result
from .paths import IoTDBPathCodec
from .schema import SCHEMA, metadata_values
from .session import IoTDBSession


def _field_double(field: Any) -> float:
    if field is None:
        return math.nan
    for name in ("get_double_value", "get_value"):
        getter = getattr(field, name, None)
        if callable(getter):
            value = getter()
            return math.nan if value is None else float(value)
    value = getattr(field, "value", field)
    return math.nan if value is None else float(value)


def _row_fields(row: Any) -> list[Any]:
    getter = getattr(row, "get_fields", None)
    if callable(getter):
        return list(getter())
    if isinstance(row, (tuple, list)):
        return list(row)
    fields = getattr(row, "fields", None)
    return list(fields) if fields is not None else []


def _normalize_matrix(values: np.ndarray) -> np.ndarray:
    matrix = np.asarray(values)
    while matrix.ndim > 2 and matrix.shape[-1] == 1:
        matrix = np.squeeze(matrix, axis=-1)
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    if matrix.ndim != 2:
        raise ValueError(f"Expected signal shape (N, C), got {matrix.shape}")
    return np.asarray(matrix, dtype=np.float64)


class IoTDBSignalStore(SignalStore, WritableSignalStore):
    """IoTDB-backed signal store with a committed-sample metadata index.

    A metadata row is written after all signal tablets. Consequently the `.meta`
    tree acts as a commit marker: interrupted imports can leave orphan signal
    series, but readers never expose a partially written sample.
    """

    availability_is_cheap = True

    def __init__(
        self,
        config: IoTDBConfig,
        metadata: MetadataCatalog | None = None,
        *,
        sample_index: _SampleIndex | None = None,
    ):
        self.config = config
        self.metadata = metadata
        self.connection = IoTDBSession(config)
        self._index: _SampleIndex | None = sample_index
        self._shape_cache: dict[str, tuple[int, int]] = {}
        self._database_ready = False

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
        enable_rpc_compression: bool = False,
        metadata: MetadataCatalog | None = None,
    ) -> "IoTDBSignalStore":
        return cls(
            IoTDBConfig(
                host,
                port,
                user,
                password,
                root,
                fetch_size,
                zone_id,
                enable_rpc_compression,
            ),
            metadata,
        )

    @property
    def session(self):
        return self.connection.open()

    def _sample_index(self) -> _SampleIndex:
        if self._index is None:
            self._index = _SampleIndex.build(self.config, self.session)
        return self._index

    def _invalidate(self, sample_id: str | int | None = None) -> None:
        self._index = None
        if sample_id is None:
            self._shape_cache.clear()
        else:
            self._shape_cache.pop(id_text(sample_id), None)

    def _resolve(self, sample_id: str | int) -> tuple[SampleMetadata, str]:
        key = id_text(sample_id)
        index = self._sample_index()
        if key not in index:
            raise KeyError(f"Sample {sample_id} not found below {self.config.root}")
        reference = index[key]
        record = (
            self.metadata.get(key)
            if self.metadata is not None and key in self.metadata
            else reference.record
        )
        return record, reference.signal_device

    def contains(self, sample_id: str | int) -> bool:
        return id_text(sample_id) in self._sample_index()

    def list_ids(self):
        return self._sample_index().keys()

    def shape(self, sample_id: str | int) -> tuple[int, int]:
        key = id_text(sample_id)
        if key in self._shape_cache:
            return self._shape_cache[key]
        record, device = self._resolve(sample_id)
        if record.sample_length is not None and record.channels is not None:
            shape = int(record.sample_length), int(record.channels)
        else:
            shape = self._shape_from_database(device)
        self._shape_cache[key] = shape
        return shape

    def _query_frame(self, sql: str):
        result = self.session.execute_query_statement(sql)
        try:
            return result.todf()
        finally:
            _close_result(result)

    def _shape_from_database(self, device: str) -> tuple[int, int]:
        count_frame = self._query_frame(f"SELECT COUNT(ch_0) FROM {device}")
        if count_frame.empty:
            length = 0
        else:
            values = [
                value
                for value in count_frame.iloc[0].tolist()
                if value is not None and not (isinstance(value, float) and np.isnan(value))
            ]
            length = int(values[-1]) if values else 0
        channels_frame = self._query_frame(f"SHOW TIMESERIES {device}.ch_*")
        channels = int(len(channels_frame))
        if channels <= 0:
            raise ValueError(f"No signal channels below {device}")
        return length, channels

    def read(
        self,
        sample_id: str | int,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        step: int = 1,
    ) -> np.ndarray:
        step = int(step)
        if step <= 0:
            raise ValueError("step must be positive")
        _, device = self._resolve(sample_id)
        length, count = self.shape(sample_id)
        selected = list(range(count)) if channels is None else [int(c) for c in channels]
        if not selected or any(c < 0 or c >= count for c in selected):
            raise IndexError("Invalid channel selection")
        start = int(start)
        end = length if end is None else min(int(end), length)
        if start < 0 or end < start or start > length:
            raise ValueError("Expected 0 <= start <= end <= length")
        if start == end:
            return np.empty((0, len(selected)), dtype=np.float64)

        measurements = [f"ch_{channel}" for channel in selected]
        sql = (
            f"SELECT {', '.join(measurements)} FROM {device} "
            f"WHERE time >= {start} AND time < {end}"
        )
        result = self.session.execute_query_statement(sql)
        try:
            if not callable(getattr(result, "has_next", None)):
                return self._read_dataframe_result(result, measurements, step)
            capacity = math.ceil((end - start) / step)
            out = np.empty((capacity, len(selected)), dtype=np.float64)
            seen = 0
            written = 0
            while result.has_next():
                fields = _row_fields(result.next())
                if seen % step == 0:
                    if written >= len(out):
                        out = np.vstack(
                            [out, np.empty_like(out[: max(1, len(out) // 2)])]
                        )
                    for column in range(len(selected)):
                        out[written, column] = (
                            _field_double(fields[column])
                            if column < len(fields)
                            else math.nan
                        )
                    written += 1
                seen += 1
            return out[:written]
        finally:
            _close_result(result)

    @staticmethod
    def _read_dataframe_result(result, measurements: list[str], step: int) -> np.ndarray:
        frame = result.todf()
        columns = [
            next(
                column
                for column in frame.columns
                if str(column) == measurement
                or str(column).endswith("." + measurement)
            )
            for measurement in measurements
        ]
        return np.asarray(frame[columns].to_numpy()[::step], dtype=np.float64)

    def ensure_database(self) -> None:
        if self._database_ready:
            return
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
        self._database_ready = True

    def write(
        self,
        sample_id: str | int,
        values: np.ndarray,
        *,
        sample_rate: float | None = None,
        name: str | None = None,
        sample_length: int | None = None,
        channels: int | None = None,
        metadata: Mapping[str, Any] | SampleMetadata | None = None,
        base_time: int = 0,
        chunk_size: int = 10000,
        mode: str = "error",
    ) -> dict[str, Any]:
        matrix = _normalize_matrix(values)
        length, count = matrix.shape
        record = self._prepare_record(
            sample_id,
            length,
            count,
            metadata,
            sample_rate=sample_rate,
            name=name,
            sample_length=sample_length,
            channels=channels,
        )
        return self._write_chunks(
            record,
            length,
            count,
            lambda start, end: matrix[start:end],
            base_time=base_time,
            chunk_size=chunk_size,
            mode=mode,
        )

    def write_from_store(
        self,
        sample_id: str | int,
        source: SignalStore,
        *,
        metadata: Mapping[str, Any] | SampleMetadata | None = None,
        base_time: int = 0,
        chunk_size: int = 10000,
        mode: str = "upsert",
    ) -> dict[str, Any]:
        shape = source.shape(sample_id)
        length = int(shape[0])
        count = 1 if len(shape) == 1 else int(shape[1])
        record = self._prepare_record(sample_id, length, count, metadata)
        return self._write_chunks(
            record,
            length,
            count,
            lambda start, end: source.read(sample_id, start, end),
            base_time=base_time,
            chunk_size=chunk_size,
            mode=mode,
        )

    def _prepare_record(
        self,
        sample_id: str | int,
        length: int,
        count: int,
        metadata: Mapping[str, Any] | SampleMetadata | None,
        **overrides: Any,
    ) -> SampleMetadata:
        key = id_text(sample_id)
        if isinstance(metadata, SampleMetadata):
            record = metadata
        else:
            mapping = dict(metadata or {})
            if not mapping and self.metadata is not None and key in self.metadata:
                record = self.metadata.get(key)
            else:
                mapping["sample_id"] = key
                for field, value in overrides.items():
                    if value is not None:
                        mapping[field] = value
                record = SampleMetadata.from_mapping(mapping)
        if id_text(record.sample_id) != key:
            raise ValueError("metadata sample_id does not match sample_id")
        supplied_length = overrides.get("sample_length", record.sample_length)
        supplied_channels = overrides.get("channels", record.channels)
        if supplied_length is not None and int(supplied_length) != length:
            raise ValueError(
                f"metadata sample_length={supplied_length} does not match values length={length}"
            )
        if supplied_channels is not None and int(supplied_channels) != count:
            raise ValueError(
                f"metadata channels={supplied_channels} does not match values channels={count}"
            )
        changes = {"sample_length": length, "channels": count}
        for field in ("sample_rate", "name"):
            if overrides.get(field) is not None:
                changes[field] = overrides[field]
        return replace(record, **changes)

    def _write_chunks(
        self,
        record: SampleMetadata,
        length: int,
        count: int,
        reader,
        *,
        base_time: int,
        chunk_size: int,
        mode: str,
    ) -> dict[str, Any]:
        chunk_size = int(chunk_size)
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if mode not in {"error", "upsert"}:
            raise ValueError("mode must be 'error' or 'upsert'")
        if mode == "error" and self.contains(record.sample_id):
            raise FileExistsError(f"Sample {record.sample_id} already exists")

        self.ensure_database()
        device = IoTDBPathCodec.signal_device(self.config, record)
        self._ensure_signal(device, count)
        chunks = 0
        for start in range(0, length, chunk_size):
            end = min(start + chunk_size, length)
            matrix = _normalize_matrix(reader(start, end))
            expected = (end - start, count)
            if matrix.shape != expected:
                raise ValueError(f"Invalid signal chunk shape {matrix.shape}; expected {expected}")
            self._insert_chunk(device, matrix, base_time + start)
            chunks += 1

        # Commit marker: publish metadata only after all signal chunks succeed.
        self._write_metadata(record, timestamp=int(base_time))
        self._invalidate(record.sample_id)
        return {
            "sample_id": record.sample_id,
            "device": device,
            "length": length,
            "channels": count,
            "chunks": chunks,
            "metadata": record.to_dict(),
        }

    def _insert_chunk(self, device: str, matrix: np.ndarray, start_time: int) -> None:
        from ...iotdb import _imports

        _, Types, _, _, Tablet = _imports()
        count = int(matrix.shape[1])
        measurements = [f"ch_{index}" for index in range(count)]
        timestamps = np.arange(
            start_time,
            start_time + int(matrix.shape[0]),
            dtype=np.int64,
        )
        tablet = Tablet(
            device,
            measurements,
            [Types.DOUBLE] * count,
            [np.asarray(matrix[:, index], dtype=np.float64) for index in range(count)],
            timestamps,
        )
        self.session.insert_aligned_tablet(tablet)

    def _ensure_signal(self, device: str, channels: int) -> None:
        from ...iotdb import _imports

        _, Types, Encoding, Compressor, _ = _imports()
        names = [f"ch_{index}" for index in range(channels)]
        missing = [
            name
            for name in names
            if not self.session.check_time_series_exists(f"{device}.{name}")
        ]
        if missing:
            self.session.create_aligned_time_series(
                device,
                missing,
                [Types.DOUBLE] * len(missing),
                [Encoding.GORILLA] * len(missing),
                [Compressor.SNAPPY] * len(missing),
            )

    def _write_metadata(self, record: SampleMetadata, timestamp: int = 0) -> None:
        from ...iotdb import _imports

        _, Types, Encoding, Compressor, _ = _imports()
        device = IoTDBPathCodec.metadata_device(self.config, record)
        names = [name for name, _ in SCHEMA]
        types = [getattr(Types, type_name) for _, type_name in SCHEMA]
        missing = [
            index
            for index, name in enumerate(names)
            if not self.session.check_time_series_exists(f"{device}.{name}")
        ]
        if missing:
            self.session.create_aligned_time_series(
                device,
                [names[index] for index in missing],
                [types[index] for index in missing],
                [Encoding.PLAIN] * len(missing),
                [Compressor.SNAPPY] * len(missing),
            )
        values = metadata_values(record)
        chosen = [
            (name, data_type, values[name])
            for name, data_type in zip(names, types)
            if values.get(name) is not None
        ]
        self.session.insert_aligned_record(
            device,
            int(timestamp),
            [item[0] for item in chosen],
            [item[1] for item in chosen],
            [item[2] for item in chosen],
        )

    def close(self) -> None:
        self.connection.close()
