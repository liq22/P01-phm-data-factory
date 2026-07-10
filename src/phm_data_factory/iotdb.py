"""Backward-compatible facade for the first-class IoTDB store backend."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .repository import PHMDataRepository


def _imports():
    """Lazy client imports; retained here for existing test and user monkeypatches."""
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
    """TCP reachability probe that does not require the IoTDB client."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


from .stores.iotdb import (  # noqa: E402: shim hooks must exist first
    IoTDBConfig,
    IoTDBImporter,
    IoTDBPathCodec,
    IoTDBSession,
    IoTDBSignalStore,
    build_iotdb_data_manifest,
    build_source_manifest,
    connect,
    load_metadata_from_iotdb,
)


def _resolve_iotdb_config(args) -> tuple[IoTDBConfig, object | None]:
    """Build IoTDBConfig from --config / PHM_DATA_CONFIG first, else CLI args."""
    cfg_path = args.config or os.getenv("PHM_DATA_CONFIG")
    repository_config = None
    if cfg_path:
        from .config import RepositoryConfig

        repository_config = RepositoryConfig.from_file(cfg_path)
    if repository_config and repository_config.iotdb:
        db = IoTDBConfig.from_mapping(repository_config.iotdb)
    else:
        db = IoTDBConfig(
            args.host,
            args.port,
            args.user,
            args.password,
            args.root,
        )
    return db, repository_config


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phm-data-iotdb")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    ingest = sub.add_parser("import")
    for command in (check, ingest):
        command.add_argument(
            "--config",
            help="RepositoryConfig file (also read via PHM_DATA_CONFIG env)",
        )
        command.add_argument("--host", default="127.0.0.1")
        command.add_argument("--port", type=int, default=6667)
        command.add_argument("--user", default="root")
        command.add_argument("--password", default="root")
        command.add_argument("--root", default="root.vibench")
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
    config, repository_config = _resolve_iotdb_config(args)
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
                        "RPC port open but session failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
            else:
                result["error"] = (
                    f"RPC port {config.port} not reachable — start IoTDB first "
                    "(cd docker/iotdb && docker compose up -d)"
                )
        else:
            metadata = args.metadata or (
                str(repository_config.metadata_path)
                if repository_config and repository_config.metadata_path
                else None
            )
            signals = args.signals or (
                str(repository_config.signal_path)
                if repository_config and repository_config.signal_path
                else None
            )
            if not metadata or not signals:
                raise ValueError(
                    "import requires --metadata and --signals "
                    "(or provide them via --config / PHM_DATA_CONFIG)"
                )
            with PHMDataRepository.from_local(
                metadata, signals
            ) as repository, IoTDBImporter(config) as importer:
                result = importer.import_repository(
                    repository,
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
                {"error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2


__all__ = [
    "IoTDBConfig",
    "IoTDBSession",
    "IoTDBPathCodec",
    "load_metadata_from_iotdb",
    "IoTDBSignalStore",
    "IoTDBImporter",
    "build_source_manifest",
    "build_iotdb_data_manifest",
    "connect",
    "main",
]
