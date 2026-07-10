"""Signal storage protocols."""

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
    """Optional capability implemented by mutable backends."""

    def write(
        self,
        sample_id: str | int,
        values: np.ndarray,
        **kwargs: Any,
    ) -> Mapping[str, Any]: ...
