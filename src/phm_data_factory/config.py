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
    dataset_manifest_path: Path | None = None
    default_max_points: int = 4096
    iotdb: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any], base_dir: Path | None = None):
        if not isinstance(mapping, Mapping):
            raise TypeError("repository config must be a mapping")
        base = base_dir or Path.cwd()
        backend = str(mapping.get("backend", "iotdb")).strip().lower()
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
        dataset_manifest = resolve(
            mapping.get("dataset_manifest_path", mapping.get("dataset_manifest"))
        )
        if backend == "local" and (metadata is None or signals is None):
            raise ValueError("Local backend requires metadata_path and signal_path")
        max_points = int(mapping.get("default_max_points", 4096))
        if max_points <= 0:
            raise ValueError("default_max_points must be positive")
        iotdb = mapping.get("iotdb", {})
        if iotdb is None:
            iotdb = {}
        if not isinstance(iotdb, Mapping):
            raise ValueError("iotdb config must be a mapping")
        return cls(
            backend,
            metadata,
            signals,
            dataset_manifest,
            max_points,
            dict(iotdb),
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
        if not isinstance(data, Mapping):
            raise ValueError("repository config file must contain a mapping")
        return cls.from_mapping(data, path.parent)

    @classmethod
    def from_environment(cls):
        if os.getenv("PHM_DATA_CONFIG"):
            return cls.from_file(os.environ["PHM_DATA_CONFIG"])
        backend = os.getenv("PHM_DATA_BACKEND", "iotdb").strip().lower()
        mapping = {
            "backend": backend,
            "metadata_path": os.getenv("PHM_DATA_METADATA"),
            "signal_path": os.getenv("PHM_DATA_SIGNALS"),
            "dataset_manifest_path": os.getenv("PHM_DATA_MANIFEST"),
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


def env_config_present() -> bool:
    """True if PHM_DATA_CONFIG points at a config file.

    Only PHM_DATA_CONFIG triggers the env path on the CLI/MCP/import entries;
    scattered PHM_DATA_*/IOTDB_* vars do NOT. This keeps the three entry points
    symmetrical (--config > PHM_DATA_CONFIG > CLI args) and prevents a stray
    IOTDB_HOST (set for import) from silently overriding --metadata/--signals
    on `phm-data`. from_environment() still honors scattered env vars when
    called directly from Python.
    """
    return bool(os.getenv("PHM_DATA_CONFIG"))


def build_repository(config: RepositoryConfig) -> PHMDataRepository:
    if config.backend == "local":
        return PHMDataRepository.from_local(config.metadata_path, config.signal_path)
    from .iotdb import IoTDBConfig, IoTDBSignalStore, load_metadata_from_iotdb

    db = IoTDBConfig.from_mapping(config.iotdb)
    if config.metadata_path:
        # External (xlsx) catalog: contains() must DB-check for correctness.
        metadata = MetadataCatalog.from_file(config.metadata_path)
        store = IoTDBSignalStore(db, metadata, availability_via_catalog=False)
    else:
        # Catalog from IoTDB: it IS the imported set → cheap, correct contains().
        metadata = load_metadata_from_iotdb(db)
        store = IoTDBSignalStore(db, metadata, availability_via_catalog=True)
    return PHMDataRepository(metadata, store)


def _coerce_config(
    config: str | Path | Mapping[str, Any] | RepositoryConfig | None = None,
    /,
    **overrides: Any,
) -> RepositoryConfig:
    if config is None:
        rc = RepositoryConfig.from_environment()
    elif isinstance(config, RepositoryConfig):
        rc = config
    elif isinstance(config, Mapping):
        rc = RepositoryConfig.from_mapping(config)
    else:
        rc = RepositoryConfig.from_file(config)
    if overrides:
        from dataclasses import replace

        rc = replace(rc, iotdb={**rc.iotdb, **overrides})
    return rc


def connect(
    config: str | Path | Mapping[str, Any] | RepositoryConfig | None = None,
    /,
    **overrides: Any,
) -> PHMDataRepository:
    """One-liner entry point for the training repository API."""

    return build_repository(_coerce_config(config, **overrides))


def connect_agent(
    config: str | Path | Mapping[str, Any] | RepositoryConfig | None = None,
    /,
    *,
    profile: str = "benchmark_public",
    dataset_digest: str | None = None,
    **overrides: Any,
):
    """Open bounded read-only Agent tools with concrete runtime identity."""

    from .agent import AgentDataTools
    from .identity import load_dataset_identity

    rc = _coerce_config(config, **overrides)
    if dataset_digest is None and rc.dataset_manifest_path is not None:
        dataset_digest = load_dataset_identity(rc.dataset_manifest_path)[
            "dataset_digest"
        ]
    backend_kind = "local_hdf5" if rc.backend == "local" else "iotdb_tree"
    return AgentDataTools(
        build_repository(rc),
        rc.default_max_points,
        profile=profile,
        backend_kind=backend_kind,
        dataset_digest=dataset_digest,
    )
