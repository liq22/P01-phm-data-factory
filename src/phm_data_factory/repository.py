"""Unified PHM repository."""

from __future__ import annotations
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np
from .metadata import MetadataCatalog
from .models import SampleMetadata, SignalWindow
from .stores import SignalStore
from .stores.base import WritableSignalStore


class PHMDataRepository:
    def __init__(self, metadata: MetadataCatalog, signals: SignalStore):
        self.metadata, self.signals = metadata, signals

    @classmethod
    def from_local(cls, metadata_path: str | Path, signal_path: str | Path):
        try:
            from .stores import DirectoryH5SignalStore, H5SignalStore
        except RuntimeError:
            raise
        except ImportError as exc:
            raise RuntimeError("Install phm-data-factory[legacy] for HDF5 support") from exc

        metadata = MetadataCatalog.from_file(metadata_path)
        path = Path(signal_path).expanduser().resolve()
        signals = (
            DirectoryH5SignalStore(path, metadata)
            if path.is_dir()
            else H5SignalStore(path)
        )
        return cls(metadata, signals)

    def summary(self) -> dict[str, Any]:
        result = self.metadata.summary()
        result["signal_store"] = type(self.signals).__name__
        if self.signals.availability_is_cheap:
            available = sum(self.signals.contains(i) for i in self.metadata.keys())
            result.update(
                signals_available=available,
                signals_missing=len(self.metadata) - available,
                availability_checked=True,
            )
        else:
            result.update(
                signals_available=None, signals_missing=None, availability_checked=False
            )
        return result

    def list_datasets(self):
        return self.metadata.list_datasets()

    def metadata_frame(self, profile: str = "canonical"):
        """Trusted training metadata; intentionally absent from Agent/MCP tools."""

        return self.metadata.to_frame(profile)

    def search_samples(
        self,
        filters: Mapping[str, Any] | None = None,
        limit: int | None = 100,
        visible_only=False,
    ):
        return [r.to_dict() for r in self.metadata.search(filters, limit, visible_only)]

    def get_sample_metadata(self, sample_id):
        result = self.metadata.get(sample_id).to_dict()
        result["signal_available"] = self.signals.contains(sample_id)
        if result["signal_available"]:
            result["stored_shape"] = list(self.signals.shape(sample_id))
        return result

    def get_signal_window(
        self,
        sample_id,
        start=0,
        end=None,
        channels: Sequence[int] | None = None,
        max_points: int | None = 4096,
    ) -> SignalWindow:
        shape = self.signals.shape(sample_id)
        length = int(shape[0])
        start = int(start)
        end = length if end is None else min(int(end), length)
        if start < 0 or end < start or start > length:
            raise ValueError("Expected 0 <= start <= end <= length")
        count = 1 if len(shape) == 1 else int(shape[1])
        selected = (
            list(range(count)) if channels is None else [int(c) for c in channels]
        )
        if not selected or any(c < 0 or c >= count for c in selected):
            raise IndexError("Invalid channel selection")
        if max_points is not None and int(max_points) <= 0:
            raise ValueError("max_points must be positive or None")
        step = (
            1
            if max_points is None
            else max(1, math.ceil(max(end - start, 0) / int(max_points)))
        )
        values = np.asarray(self.signals.read(sample_id, start, end, selected, step))
        while values.ndim > 2 and values.shape[-1] == 1:
            values = np.squeeze(values, axis=-1)
        if values.ndim == 1:
            values = values[:, None]
        record = self.metadata.get(sample_id)
        return SignalWindow(
            str(sample_id),
            start,
            end,
            step,
            tuple(selected),
            record.sample_rate,
            values,
        )

    def read_signal(
        self,
        sample_id,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
    ) -> np.ndarray:
        """Training path: return the raw signal window as an ndarray, NO decimation.

        This is the v0.2 stable read op for PHM-Vibench (Dataset/DataLoader want
        a dense ndarray, not a bounded preview). For bounded Agent/JSON previews
        use ``get_signal_window`` (which applies ``max_points`` decimation).
        """
        return self.get_signal_window(sample_id, start, end, channels, None).values

    def write_sample(
        self,
        sample_id,
        values: np.ndarray,
        metadata: Mapping[str, Any] | SampleMetadata | None = None,
        *,
        mode: str = "error",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """v0.2 stable write op. ``mode``: ``"error"`` (default) raises if the
        sample already exists; ``"overwrite"`` replaces it. Raises ``TypeError``
        if the backend is read-only (e.g. HDF5).
        """
        store = self.signals
        if not isinstance(store, WritableSignalStore):
            raise TypeError(
                f"{type(store).__name__} is read-only; write is only supported "
                "on writable backends (e.g. IoTDB)"
            )
        return dict(
            store.write(sample_id, values, metadata=metadata, mode=mode, **kwargs)
        )

    def get_signal_statistics(
        self, sample_id, start=0, end=None, channels=None, max_points=100000
    ):
        window = self.get_signal_window(sample_id, start, end, channels, max_points)
        values = np.asarray(window.values, dtype=float)
        if values.ndim > 2:
            values = values.reshape(values.shape[0], values.shape[1], -1).mean(axis=2)
        stats = []
        for index, channel in enumerate(window.channels):
            finite = values[:, index][np.isfinite(values[:, index])]
            stats.append(
                {"channel": channel, "count": int(finite.size)}
                if not finite.size
                else {
                    "channel": channel,
                    "count": int(finite.size),
                    "mean": float(finite.mean()),
                    "std": float(finite.std()),
                    "min": float(finite.min()),
                    "max": float(finite.max()),
                    "rms": float(np.sqrt(np.mean(finite**2))),
                    "peak_to_peak": float(np.ptp(finite)),
                }
            )
        return {
            "sample_id": str(sample_id),
            "start": window.start,
            "end": window.end,
            "step": window.step,
            "approximate": window.step > 1,
            "channels": stats,
        }

    def validate_sample(self, sample_id):
        record = self.metadata.get(sample_id)
        errors = []
        warnings = []
        if not self.signals.contains(sample_id):
            return {
                "sample_id": str(sample_id),
                "valid": False,
                "errors": ["Signal data is missing"],
                "warnings": [],
            }
        shape = self.signals.shape(sample_id)
        channels = 1 if len(shape) == 1 else int(shape[1])
        if record.sample_length is not None and shape[0] != record.sample_length:
            errors.append("Sample length mismatch")
        if record.channels is not None and channels != record.channels:
            errors.append("Channel count mismatch")
        if len(shape) > 2:
            warnings.append(f"Trailing dimensions retained in cache: {list(shape)}")
        return {
            "sample_id": str(sample_id),
            "valid": not errors,
            "stored_shape": list(shape),
            "metadata_sample_length": record.sample_length,
            "metadata_channels": record.channels,
            "errors": errors,
            "warnings": warnings,
        }

    def close(self):
        self.signals.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
