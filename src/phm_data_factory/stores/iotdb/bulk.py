"""Bulk H5 → IoTDB import + data manifest builders.

``IoTDBImporter.import_sample`` is a thin orchestrator that delegates the actual
write to ``IoTDBSignalStore.write`` (the single write path). The public surface
(``SCHEMA``, ``import_sample``, ``import_repository``) is unchanged so
``scripts/import_datasets.py`` / ``verify_metadata.py`` and the existing tests
keep working.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...repository import PHMDataRepository
from .config import IoTDBConfig
from .schema import SCHEMA
from .session import IoTDBSession
from .store import IoTDBSignalStore


class IoTDBImporter:
    SCHEMA = SCHEMA  # back-compat: verify_metadata.py reads IoTDBImporter.SCHEMA

    def __init__(self, config: IoTDBConfig):
        self.config, self.connection = config, IoTDBSession(config)

    @property
    def session(self):
        return self.connection.open()

    def import_sample(
        self, repository: PHMDataRepository, sample_id, chunk_size=10000
    ) -> dict[str, Any]:
        if int(chunk_size) <= 0:
            raise ValueError("chunk_size must be positive")
        validation = repository.validate_sample(sample_id)
        if not validation["valid"]:
            raise ValueError(validation["errors"])
        record = repository.metadata.get(sample_id)
        # Delegate to the store's single write path; share this importer's
        # session so callers (and tests) that inject ``importer.connection``
        # drive the write through the expected session.
        store = IoTDBSignalStore(
            self.config, repository.metadata, availability_via_catalog=False
        )
        store.connection = self.connection
        return store.write(
            sample_id,
            repository.signals.read(sample_id),
            metadata=record,
            chunk_size=chunk_size,
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
            r.sample_id
            for r in repository.metadata.search(limit=None, visible_only=visible_only)
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
                self.config, repository, imported, failed, source_manifest
            ),
        }

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


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


def build_source_manifest(metadata_path: str | Path, signal_path: str | Path) -> dict[str, Any]:
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
        p
        for p in signals.iterdir()
        if p.is_file() and p.suffix.lower() in {".h5", ".hdf5"}
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
        "signal_path_pattern": f"{config.root}.<dataset>.sample_<Id>.signal.ch_<channel>",
        "metadata_path_pattern": f"{config.root}.<dataset>.sample_<Id>.meta.<field>",
        "metadata_fields": [name for name, _ in SCHEMA],
        "source": dict(source_manifest or {}),
        "sample_ids": repository.metadata.keys(),
        "imported_sample_ids": [str(item["sample_id"]) for item in imported],
        "failed_sample_ids": [str(item["sample_id"]) for item in failed],
    }
