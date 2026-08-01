"""IoTDB connection configuration."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class IoTDBConfig:
    host: str = "127.0.0.1"
    port: int = 6667
    user: str = "root"
    password: str = "root"
    root: str = "root.vibench"
    fetch_size: int = 5000
    zone_id: str = "UTC"

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]):
        return cls(
            str(m.get("host", "127.0.0.1")),
            int(m.get("port", 6667)),
            str(m.get("user", m.get("username", "root"))),
            str(m.get("password", "root")),
            str(m.get("root", "root.vibench")).rstrip("."),
            int(m.get("fetch_size", 5000)),
            str(m.get("zone_id", "UTC")),
        )
