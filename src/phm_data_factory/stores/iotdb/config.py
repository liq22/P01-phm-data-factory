"""IoTDB connection configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IoTDBConfig:
    host: str = "127.0.0.1"
    port: int = 6667
    user: str = "root"
    password: str = "root"
    root: str = "root.vibench"
    fetch_size: int = 5000
    zone_id: str = "UTC"
    enable_rpc_compression: bool = False

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]):
        return cls(
            str(mapping.get("host", "127.0.0.1")),
            int(mapping.get("port", 6667)),
            str(mapping.get("user", mapping.get("username", "root"))),
            str(mapping.get("password", "root")),
            str(mapping.get("root", "root.vibench")).rstrip("."),
            int(mapping.get("fetch_size", 5000)),
            str(mapping.get("zone_id", "UTC")),
            _as_bool(
                mapping.get(
                    "enable_rpc_compression",
                    mapping.get("rpc_compression", False),
                )
            ),
        )
