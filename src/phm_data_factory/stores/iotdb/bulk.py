"""Bulk migration helpers and ergonomic repository connection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...config import RepositoryConfig, build_repository
from ...repository import PHMDataRepository
from .config import IoTDBConfig
from .schema import SCHEMA
from .store import IoTDBSignalStore


class IoTDBImporter:
    """Backward-compatible bulk importer backed by IoTDBSignalStore.write."""

    SCHEMA = SCHEMA

    def __init__(self, config: IoTDBConfig):
        self.config = config
        self.store = IoTDBSignalStore(config)

    @property
    def connection(self):
        return self.store.connection

    @connection.setter
    def connection(self, value):
        self.store.connection = value

    @property
    def session(self):
        return self.store.session

    def ensure_database(self):
        self.store.ensure_database()

    def import_sample(
        self,
        repository: PHMDataRepository,
        sample_id,
        chunk_size: int = 10000,
    ) -> dict[str, Any]:
        if int(chunk_size) <= 0:
            raise ValueError("chunk_size must be positive")
        validation = repository.validate_sample(sample_id)
        if not validation["valid"]:
            raise ValueError(validation["errors"])
        record = repository.metadata.get(sample_id)
        # Preserve the existing chunked source-read behavior. Reading the whole
        # HDF5 sample before writing would multiply peak memory for large data.
        return self.store.write_from_store(
            sample_id,
            repository.signals,
            metadata=record,
            chunk_size=chunk_size,
            mode="upsert",
        )

    def import_repository(
        self,
        repository,
        sample_ids=None,
        chunk_size=10000,
        visible_only=False,
        continue_on_error=False,
        source_manifest: Mapping[str, Any] | None = None,
    ):
        ids = sample_ids or [
            record.sample_id
            for record in repository.metadata.search(
                limit=None, visible_only=visible_only
            )
        ]
        imported, failed = [], []
        for sample_id in ids:
            try:
                imported.append(self.import_sample(repository, sample_id, chunk_size))
            except Exception as exc:
                failed.append({"sample_id": str(sample_id), "error": str(exc)})
                if not continue_on_error:
                    raise
        return {
            "root": self.config.root,
            "imported_count": len(imported),
            "failed_count": len(failed),
            "imported": imported,
            "failed": failed,
            "data_manifest": build_iotdb_data_manifest(
                self.config,
                repository,
                imported,
                failed,
                source_manifest,
            ),
        }

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def connect(
    config: str | Path | Mapping[str, Any] | RepositoryConfig | None = None,
    **overrides: Any,
) -> PHMDataRepository:
    """Build a repository from env, a mapping, a config file, or an existing config.

    Unknown top-level overrides are treated as IoTDB connection fields, making
    ``connect(host="db", root="root.vibench")`` the concise direct form.
    """
    if config is None:
        repository_config = RepositoryConfig.from_environment()
    elif isinstance(config, RepositoryConfig):
        repository_config = config
    elif isinstance(config, Mapping):
        repository_config = RepositoryConfig.from_mapping(config)
    else:
        repository_config = RepositoryConfig.from_file(config)

    if overrides:
        values = dict(overrides)
        nested = dict(values.pop("iotdb", {}) or {})
        top_level = {
            key: values.pop(key)
            for key in tuple(values)
            if key in {"backend", "metadata_path", "signal_path", "default_max_points"}
        }
        merged_iotdb = dict(repository_config.iotdb)
        merged_iotdb.update(nested)
        merged_iotdb.update(values)
        replacements: dict[str, Any] = {"iotdb": merged_iotdb}
        replacements.update(top_level)
        for field in ("metadata_path", "signal_path"):
            if field in replacements and replacements[field] is not None:
                replacements[field] = Path(replacements[field]).expanduser().resolve()
        if "default_max_points" in replacements:
            replacements["default_max_points"] = int(replacements["default_max_points"])
        repository_config = replace(repository_config, **replacements)
    return build_repository(repository_config)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_manifest(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": int(stat.st_size),
        "sha256": _sha256_file(path),
    }


def build_source_manifest(
    metadata_path: str | Path, signal_path: str | Path
) -> dict[str, Any]:
    metadata = Path(metadata_path).expanduser().resolve()
    signals = Path(signal_path).expanduser().resolve()
    result: dict[str, Any] = {
        "metadata": _file_manifest(metadata),
        "signals": {
            "path": str(signals),
            "kind": "directory" if signals.is_dir() else "file",
        },
    }
    if signals.is_file():
        result["signals"].update(_file_manifest(signals))
        return result
    signal_files = sorted(
        path
        for path in signals.iterdir()
        if path.is_file() and path.suffix.lower() in {".h5", ".hdf5"}
    )
    files = [_file_manifest(path) for path in signal_files]
    inventory = json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")
    result["signals"].update(
        {
            "file_count": len(files),
            "inventory_sha256": hashlib.sha256(inventory).hexdigest(),
            "files": files,
        }
    )
    return result


def build_iotdb_data_manifest(
    config: IoTDBConfig,
    repository: PHMDataRepository,
    imported: Sequence[Mapping[str, Any]],
    failed: Sequence[Mapping[str, Any]],
    source_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "phm-data-factory/iotdb-data-manifest-v1",
        "backend": "iotdb",
        "root": config.root,
        "path_model": "tree",
        "metadata_query": f"SELECT * FROM {config.root}.**.meta ALIGN BY DEVICE",
        "signal_path_pattern": (
            f"{config.root}.<dataset>.sample_<Id>.signal.ch_<channel>"
        ),
        "metadata_path_pattern": (
            f"{config.root}.<dataset>.sample_<Id>.meta.<field>"
        ),
        "metadata_fields": [name for name, _ in SCHEMA],
        "source": dict(source_manifest or {}),
        "sample_ids": repository.metadata.keys(),
        "imported_sample_ids": [str(item["sample_id"]) for item in imported],
        "failed_sample_ids": [str(item["sample_id"]) for item in failed],
    }
