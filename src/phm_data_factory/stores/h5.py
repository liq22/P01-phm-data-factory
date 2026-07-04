"""HDF5 signal stores."""

from __future__ import annotations
from pathlib import Path
from typing import Iterable, Iterator, Sequence
import h5py
import numpy as np
from .base import SignalStore
from ..metadata import MetadataCatalog
from ..models import id_text


def candidate_keys(sample_id: str | int) -> tuple[str, ...]:
    key = id_text(sample_id)
    return key, f"Id_{key}", f"sample_{key}"


class H5SignalStore(SignalStore):
    availability_is_cheap = True

    def __init__(self, path: str | Path, mode: str = "r"):
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.mode, self._handle = mode, None

    def _open(self):
        if self._handle is None or not self._handle.id.valid:
            self._handle = h5py.File(
                self.path, self.mode, libver="latest", swmr=self.mode == "r"
            )
        return self._handle

    def _key(self, sample_id):
        handle = self._open()
        for key in candidate_keys(sample_id):
            if key in handle:
                return key
        raise KeyError(f"Sample {sample_id} not found in {self.path}")

    def read(self, sample_id, start=0, end=None, channels=None, step=1):
        if step <= 0:
            raise ValueError("step must be positive")
        dataset = self._open()[self._key(sample_id)]
        length = int(dataset.shape[0])
        end = length if end is None else min(int(end), length)
        if start < 0 or end < start or start > length:
            raise ValueError("Expected 0 <= start <= end <= length")
        array = np.asarray(dataset[int(start) : end : step])
        if array.ndim == 1:
            array = array[:, None]
        if channels is not None:
            ids = [int(c) for c in channels]
            for c in ids:
                if c < 0 or c >= array.shape[1]:
                    raise IndexError(f"Channel {c} out of range")
            array = array[:, ids, ...]
        return array

    def shape(self, sample_id):
        return tuple(int(x) for x in self._open()[self._key(sample_id)].shape)

    def contains(self, sample_id):
        return any(k in self._open() for k in candidate_keys(sample_id))

    def list_ids(self) -> Iterable[str]:
        return tuple(str(k) for k in self._open().keys())

    def close(self):
        if self._handle is not None:
            self._handle.close()
            self._handle = None


class DirectoryH5SignalStore(SignalStore):
    availability_is_cheap = True

    def __init__(self, root: str | Path, metadata: MetadataCatalog):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise FileNotFoundError(self.root)
        self.metadata, self._stores = metadata, {}

    def _store(self, sample_id):
        record = self.metadata.get(sample_id)
        candidates = [self.root / "cache.h5"]
        if record.name:
            candidates.append(self.root / f"{record.name}.h5")
        if record.file and record.file.lower().endswith((".h5", ".hdf5")):
            candidates.append(self.root / record.file)
        for path in candidates:
            if not path.exists():
                continue
            store = self._stores.setdefault(path, H5SignalStore(path))
            if store.contains(sample_id):
                return store
        raise KeyError(f"Sample {sample_id} not found below {self.root}")

    def read(self, sample_id, start=0, end=None, channels=None, step=1):
        return self._store(sample_id).read(sample_id, start, end, channels, step)

    def shape(self, sample_id):
        return self._store(sample_id).shape(sample_id)

    def contains(self, sample_id):
        try:
            self._store(sample_id)
            return True
        except (KeyError, FileNotFoundError):
            return False

    def list_ids(self):
        return tuple(self.metadata.keys())

    def close(self):
        for store in self._stores.values():
            store.close()
        self._stores.clear()


class H5DataDict:
    """Legacy PHM-Vibench dict-like wrapper; returns the original cache shape."""

    def __init__(self, h5file: str | Path, mode: str = "r"):
        self.store, self.h5_file = H5SignalStore(h5file, mode), str(h5file)

    def __getitem__(self, key):
        return self.store.read(key)

    def __contains__(self, key):
        return self.store.contains(key)

    def keys(self):
        return set(self.store.list_ids())

    def items(self) -> Iterator[tuple[str | int, np.ndarray]]:
        for key in self.keys():
            try:
                public = int(key)
            except ValueError:
                public = key
            yield public, self.store.read(key)

    def __len__(self):
        return len(self.keys())

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
