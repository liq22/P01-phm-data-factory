"""Signal storage protocol.

`SignalStore` is the read-only contract every backend implements.
`WritableSignalStore` is an *optional* capability Protocol — backends that can
accept writes (e.g. IoTDB) implement it; read-only backends (e.g. HDF5) do not.
The repository capability-checks with `isinstance(store, WritableSignalStore)`.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable
import numpy as np


class SignalStore(ABC):
    availability_is_cheap = False

    @abstractmethod
    def read(
        self,
        sample_id: str | int,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        step: int = 1,
    ) -> np.ndarray: ...

    @abstractmethod
    def shape(self, sample_id: str | int) -> tuple[int, ...]: ...

    @abstractmethod
    def contains(self, sample_id: str | int) -> bool: ...

    @abstractmethod
    def list_ids(self) -> Iterable[str]: ...

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


@runtime_checkable
class WritableSignalStore(Protocol):
    """Optional write capability for a SignalStore.

    `mode`: ``"error"`` raises if the sample already exists; ``"overwrite"``
    replaces it. Deletion of an existing sample is scoped inside ``write`` and
    is NOT a separate public API (v0.2 contract).
    """

    def write(
        self,
        sample_id: str | int,
        values: np.ndarray,
        *,
        metadata: Mapping[str, Any] | None = None,
        mode: str = "error",
        **kwargs: Any,
    ) -> Mapping[str, Any]: ...

