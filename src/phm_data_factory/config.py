"""Repository configuration."""

from __future__ import annotations
import json, os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from .metadata import MetadataCatalog
from .repository import PHMDataRepository


@dataclass(frozen=True)
class RepositoryConfig:
    backend: str
    metadata_path: Path | None = None
    signal_path: Path | None = None
    default_max_points: int = 4096
    iotdb: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any], base_dir: Path | None = None):
        base = base_dir or Path.cwd()
        backend = str(mapping.get("backend", "iotdb")).lower()
        if backend not in {"local", "iotdb"}:
            raise ValueError(f"Unsupported backend: {backend}")
        resolve = lambda v: (
            None
            if not v
            else (
                (base / Path(str(v))).resolve()
                if not Path(str(v)).is_absolute()
                else Path(str(v)).resolve()
            )
        )
        metadata = resolve(mapping.get("metadata_path", mapping.get("metadata")))
        signals = resolve(mapping.get("signal_path", mapping.get("signals")))
        if backend == "local" and (metadata is None or signals is None):
            raise ValueError("Local backend requires metadata_path and signal_path")
        max_points = int(mapping.get("default_max_points", 4096))
        if max_points <= 0:
            raise ValueError("default_max_points must be positive")
        return cls(
            backend, metadata, signals, max_points, dict(mapping.get("iotdb", {}))
        )

    @classmethod
    def from_file(cls, path: str | Path):
        path = Path(path).expanduser().resolve()
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("Install phm-data-factory[yaml]") from exc
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = data or {}
        return cls.from_mapping(data, path.parent)

    @classmethod
    def from_environment(cls):
        if os.getenv("PHM_DATA_CONFIG"):
            return cls.from_file(os.environ["PHM_DATA_CONFIG"])
        backend = os.getenv("PHM_DATA_BACKEND", "iotdb")
        mapping = {
            "backend": backend,
            "metadata_path": os.getenv("PHM_DATA_METADATA"),
            "signal_path": os.getenv("PHM_DATA_SIGNALS"),
            "default_max_points": os.getenv("PHM_DATA_MAX_POINTS", "4096"),
        }
        if backend == "iotdb":
            mapping["iotdb"] = {
                "host": os.getenv("IOTDB_HOST", "127.0.0.1"),
                "port": int(os.getenv("IOTDB_PORT", "6667")),
                "user": os.getenv("IOTDB_USER", "root"),
                "password": os.getenv("IOTDB_PASSWORD", "root"),
                "root": os.getenv("IOTDB_ROOT", "root.vibench"),
                "fetch_size": int(os.getenv("IOTDB_FETCH_SIZE", "5000")),
                "zone_id": os.getenv("IOTDB_ZONE_ID", "UTC"),
            }
        return cls.from_mapping(mapping)


_ENV_CONFIG_KEYS = (
    "PHM_DATA_CONFIG",
    "PHM_DATA_BACKEND",
    "PHM_DATA_METADATA",
    "PHM_DATA_SIGNALS",
    "PHM_DATA_MAX_POINTS",
    "IOTDB_HOST",
    "IOTDB_PORT",
    "IOTDB_USER",
    "IOTDB_PASSWORD",
    "IOTDB_ROOT",
    "IOTDB_FETCH_SIZE",
    "IOTDB_ZONE_ID",
)


def env_config_present() -> bool:
    """True if any PHM_DATA_* / IOTDB_* env var is set (activates from_environment)."""
    return any(os.getenv(k) for k in _ENV_CONFIG_KEYS)


def build_repository(config: RepositoryConfig) -> PHMDataRepository:
    if config.backend == "local":
        return PHMDataRepository.from_local(config.metadata_path, config.signal_path)
    from .iotdb import IoTDBConfig, IoTDBSignalStore, load_metadata_from_iotdb

    db = IoTDBConfig.from_mapping(config.iotdb)
    metadata = (
        MetadataCatalog.from_file(config.metadata_path)
        if config.metadata_path
        else load_metadata_from_iotdb(db)
    )
    return PHMDataRepository(metadata, IoTDBSignalStore(db, metadata))
