"""Back-compat shim.

The real implementation lives in :mod:`phm_data_factory.stores.iotdb`. This
module keeps every historical import path working — ``config.py``'s
``build_repository``, ``scripts/import_datasets.py`` / ``verify_metadata.py``,
the ``phm-data-iotdb`` console entry point, and the tests' ``monkeypatch`` of
``phm_data_factory.iotdb._imports`` / ``.IoTDBSession`` / ``._probe_socket``.

``_imports`` is the canonical lazy loader and is resolved by the subpackage
(via ``from ... import iotdb as _shim``) at call time, so monkeypatching it here
propagates to ``IoTDBImporter`` / ``IoTDBSession``.
"""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from .stores.iotdb.bulk import (
    IoTDBImporter,
    build_iotdb_data_manifest,
    build_source_manifest,
)
from .stores.iotdb.config import IoTDBConfig
from .stores.iotdb.metadata import load_metadata_from_iotdb
from .stores.iotdb.paths import IoTDBPathCodec
from .stores.iotdb.session import IoTDBSession
from .stores.iotdb.store import IoTDBSignalStore

__all__ = [
    "IoTDBConfig",
    "IoTDBPathCodec",
    "IoTDBSession",
    "load_metadata_from_iotdb",
    "IoTDBSignalStore",
    "IoTDBImporter",
    "build_source_manifest",
    "build_iotdb_data_manifest",
    "main",
    "_resolve_iotdb_config",
    "_probe_socket",
    "_imports",
]


def _imports():
    try:
        from iotdb.Session import Session
        from iotdb.utils.IoTDBConstants import Compressor, TSDataType, TSEncoding
        from iotdb.utils.NumpyTablet import NumpyTablet
    except ImportError as exc:
        raise RuntimeError(
            "Install phm-data-factory with its runtime dependencies"
        ) from exc
    return Session, TSDataType, TSEncoding, Compressor, NumpyTablet


def _probe_socket(host: str, port: int, timeout: float = 5.0) -> bool:
    """TCP reachability probe — runs without the apache-iotdb client installed.

    Uses create_connection so IPv6-only localhost (::1) is not missed.
    """
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_iotdb_config(args) -> tuple[IoTDBConfig, Any]:
    """Build IoTDBConfig from --config / PHM_DATA_CONFIG first, else CLI args.

    Returns (iotdb_config, repository_config_or_none).
    """
    cfg_path = args.config or os.getenv("PHM_DATA_CONFIG")
    rc = None
    if cfg_path:
        from .config import RepositoryConfig

        rc = RepositoryConfig.from_file(cfg_path)
    if rc and rc.iotdb:
        db = IoTDBConfig.from_mapping(rc.iotdb)
    else:
        db = IoTDBConfig(args.host, args.port, args.user, args.password, args.root)
    return db, rc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phm-data-iotdb")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    ingest = sub.add_parser("import")
    for p in (check, ingest):
        p.add_argument(
            "--config",
            help="RepositoryConfig file (also read via PHM_DATA_CONFIG env)",
        )
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=6667)
        p.add_argument("--user", default="root")
        p.add_argument("--password", default="root")
        p.add_argument("--root", default="root.vibench")
    ingest.add_argument(
        "--metadata", help="metadata file (or set via --config / PHM_DATA_CONFIG)"
    )
    ingest.add_argument(
        "--signals", help="signal dir/file (or set via --config / PHM_DATA_CONFIG)"
    )
    ingest.add_argument("--sample-id", action="append", dest="sample_ids")
    ingest.add_argument("--chunk-size", type=int, default=10000)
    ingest.add_argument("--visible-only", action="store_true")
    ingest.add_argument("--continue-on-error", action="store_true")
    ingest.add_argument("--report")
    args = parser.parse_args(argv)
    config, rc = _resolve_iotdb_config(args)
    try:
        if args.command == "check":
            rpc_open = _probe_socket(config.host, config.port)
            result = {
                "host": config.host,
                "port": config.port,
                "rpc_port_open": rpc_open,
                "connected": False,
            }
            if rpc_open:
                try:
                    with IoTDBSession(config):
                        result["connected"] = True
                except Exception as exc:
                    result["error"] = (
                        f"RPC port open but session failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
            else:
                result["error"] = (
                    f"RPC port {config.port} not reachable — start IoTDB first "
                    "(cd docker/iotdb && docker compose up -d)"
                )
        else:
            from .repository import PHMDataRepository

            metadata = args.metadata or (
                str(rc.metadata_path) if rc and rc.metadata_path else None
            )
            signals = args.signals or (
                str(rc.signal_path) if rc and rc.signal_path else None
            )
            if not metadata or not signals:
                raise ValueError(
                    "import requires --metadata and --signals "
                    "(or provide them via --config / PHM_DATA_CONFIG)"
                )
            with PHMDataRepository.from_local(
                metadata, signals
            ) as repo, IoTDBImporter(config) as importer:
                result = importer.import_repository(
                    repo,
                    args.sample_ids,
                    args.chunk_size,
                    args.visible_only,
                    args.continue_on_error,
                    build_source_manifest(metadata, signals),
                )
            if args.report:
                Path(args.report).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "check" and not result.get("connected"):
            return 3
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False
            )
        )
        return 2
