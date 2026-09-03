"""Read-only signal store for one CSV file per measurement record."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .base import SignalStore
from ..metadata import MetadataCatalog


class DirectoryCSVSignalStore(SignalStore):
    """Read bounded rows from a directory tree named by trusted metadata."""

    availability_is_cheap = True

    def __init__(
        self,
        root: str | Path,
        metadata: MetadataCatalog,
        *,
        value_columns: Sequence[str],
        source_columns: Sequence[str] | None = None,
        segment_start_field: str | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(self.root)
        columns = tuple(value_columns)
        if (
            not columns
            or any(not isinstance(column, str) or not column for column in columns)
            or len(set(columns)) != len(columns)
        ):
            raise ValueError("value_columns must be unique non-empty strings")
        registered_source = columns if source_columns is None else tuple(source_columns)
        if (
            not registered_source
            or any(
                not isinstance(column, str) or not column
                for column in registered_source
            )
            or len(set(registered_source)) != len(registered_source)
            or any(column not in registered_source for column in columns)
        ):
            raise ValueError(
                "source_columns must be unique non-empty strings containing value_columns"
            )
        if segment_start_field is not None and (
            not isinstance(segment_start_field, str) or not segment_start_field.strip()
        ):
            raise ValueError("segment_start_field must be a non-empty string or None")
        self.metadata = metadata
        self.value_columns = columns
        self.source_columns = registered_source
        self.segment_start_field = segment_start_field
        self._headers: dict[Path, tuple[str, ...]] = {}
        self._validated_extents: dict[Path, int] = {}

    @staticmethod
    def _field(row: dict[str, object], *names: str) -> object | None:
        lowered = {str(key).lower(): value for key, value in row.items()}
        for name in names:
            if name.lower() in lowered:
                return lowered[name.lower()]
        return None

    @staticmethod
    def _safe_relative(value: object, field: str) -> PurePosixPath:
        text = str(value or "").strip().replace("\\", "/")
        relative = PurePosixPath(text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{field} must be a relative path without traversal")
        return relative

    def _path(self, sample_id: str | int) -> Path:
        row = self.metadata.raw(sample_id)
        filename = self._field(row, "File", "Filename")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("CSV metadata must provide File or Filename")
        folder = self._field(row, "FolderPath")
        relative = self._safe_relative(folder, "FolderPath") / self._safe_relative(
            filename, "File"
        )
        path = (self.root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("CSV signal path escapes the registered root")
        return path

    def _header(self, path: Path) -> tuple[str, ...]:
        cached = self._headers.get(path)
        if cached is not None:
            return cached
        header = tuple(str(column) for column in pd.read_csv(path, nrows=0).columns)
        if header != self.source_columns:
            raise ValueError(
                "CSV signal columns differ from the registered source_columns"
            )
        self._headers[path] = header
        return header

    def _length(self, sample_id: str | int) -> int:
        length = self.metadata.get(sample_id).sample_length
        if length is None or length <= 0:
            raise ValueError("CSV metadata must provide a positive sample length")
        return int(length)

    def _segment_start(self, sample_id: str | int) -> int:
        if self.segment_start_field is None:
            return 0
        raw = self.metadata.raw(sample_id)
        value = self._field(raw, self.segment_start_field)
        if value is None or str(value).strip() == "":
            raise ValueError(f"CSV metadata must provide {self.segment_start_field}")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"CSV metadata {self.segment_start_field} must be an integer"
            ) from exc
        if not np.isfinite(numeric) or not numeric.is_integer():
            raise ValueError(
                f"CSV metadata {self.segment_start_field} must be an integer"
            )
        start = int(numeric)
        if start < 0:
            raise ValueError(
                f"CSV metadata {self.segment_start_field} must be non-negative"
            )
        return start

    def _validate_extent(
        self,
        path: Path,
        header: tuple[str, ...],
        sample_id: str | int,
    ) -> None:
        registered_end = self._segment_start(sample_id) + self._length(sample_id)
        if self._validated_extents.get(path, 0) >= registered_end:
            return
        last_registered_row = pd.read_csv(
            path,
            header=None,
            names=list(header),
            skiprows=registered_end,
            nrows=1,
            usecols=[self.value_columns[0]],
        )
        if len(last_registered_row) != 1:
            raise ValueError("CSV signal is shorter than its registered sample length")
        self._validated_extents[path] = registered_end

    def read(
        self,
        sample_id: str | int,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        step: int = 1,
    ) -> np.ndarray:
        if step <= 0:
            raise ValueError("step must be positive")
        path = self._path(sample_id)
        header = self._header(path)
        length = self._length(sample_id)
        source_start = self._segment_start(sample_id)
        start = int(start)
        end = length if end is None else min(int(end), length)
        if start < 0 or end < start or start > length:
            raise ValueError("Expected 0 <= start <= end <= length")

        count = end - start
        if count == 0:
            values = np.empty((0, len(self.value_columns)), dtype=np.float64)
        else:
            frame = pd.read_csv(
                path,
                header=None,
                names=list(header),
                skiprows=source_start + start + 1,
                nrows=count,
                usecols=list(self.value_columns),
            )
            if len(frame) != count:
                raise ValueError("CSV signal is shorter than its registered sample length")
            # pandas evaluates ``usecols`` in source-file order.  Re-project
            # explicitly so public channel indices always follow the
            # registered ``value_columns`` contract.
            frame = frame.loc[:, list(self.value_columns)]
            try:
                values = frame.to_numpy(dtype=np.float64, copy=True)[:: int(step)]
            except (TypeError, ValueError) as exc:
                raise ValueError("CSV signal values must be numeric") from exc

        selected = (
            list(range(len(self.value_columns)))
            if channels is None
            else [int(channel) for channel in channels]
        )
        if not selected or any(
            channel < 0 or channel >= len(self.value_columns) for channel in selected
        ):
            raise IndexError("Invalid channel selection")
        return values[:, selected]

    def shape(self, sample_id: str | int) -> tuple[int, ...]:
        path = self._path(sample_id)
        header = self._header(path)
        self._validate_extent(path, header, sample_id)
        return self._length(sample_id), len(self.value_columns)

    def contains(self, sample_id: str | int) -> bool:
        try:
            return self._path(sample_id).is_file()
        except (KeyError, ValueError):
            return False

    def list_ids(self) -> Iterable[str]:
        return tuple(
            sample_id for sample_id in self.metadata.keys() if self.contains(sample_id)
        )
