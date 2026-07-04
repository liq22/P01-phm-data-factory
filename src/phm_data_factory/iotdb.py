"""Optional Apache IoTDB backend and Vibench importer."""

from __future__ import annotations
import argparse, hashlib, json, os, re, unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import numpy as np
import pandas as pd
from .metadata import MetadataCatalog
from .models import SampleMetadata, clean_value
from .repository import PHMDataRepository
from .stores import SignalStore


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


class IoTDBPathCodec:
    @staticmethod
    def segment(value: Any, allow_digit=False):
        raw = str(value).strip()
        norm = unicodedata.normalize("NFKC", raw)
        safe = re.sub(r"[^A-Za-z0-9_]", "_", norm)
        safe = re.sub(r"_+", "_", safe).strip("_") or "item"
        if safe[0].isdigit() and not allow_digit:
            safe = "x_" + safe
        if safe != norm:
            safe += "_" + hashlib.sha1(raw.encode()).hexdigest()[:8]
        return safe

    @classmethod
    def signal_device(cls, config, record):
        dataset = cls.segment(
            record.name or f"dataset_{record.dataset_id or 'unknown'}"
        )
        return f"{config.root}.{dataset}.sample_{cls.segment(record.sample_id, True)}.signal"

    @classmethod
    def metadata_device(cls, config, record):
        return cls.signal_device(config, record).rsplit(".", 1)[0] + ".meta"


class IoTDBSession:
    def __init__(self, config):
        self.config, self.session = config, None

    def open(self):
        if self.session is None:
            Session, *_ = _imports()
            self.session = Session(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                fetch_size=self.config.fetch_size,
                zone_id=self.config.zone_id,
            )
            self.session.open(enable_rpc_compression=False)
        return self.session

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def load_metadata_from_iotdb(config: IoTDBConfig) -> MetadataCatalog:
    with IoTDBSession(config) as session:
        result = session.execute_query_statement(
            f"SELECT * FROM {config.root}.**.meta ALIGN BY DEVICE"
        )
        try:
            frame = result.todf()
        finally:
            close = getattr(result, "close_operation_handle", None)
            if callable(close):
                close()
    if frame.empty:
        raise ValueError(f"No metadata below {config.root}")
    rename = {}
    for col in frame.columns:
        name = str(col)
        rename[col] = (
            name.lower()
            if name.lower() in {"time", "device"}
            else name.rsplit(".", 1)[-1]
        )
    frame = frame.rename(columns=rename)
    if "sample_id" not in frame and "device" in frame:
        frame["sample_id"] = frame["device"].map(
            lambda x: (re.search(r"\.sample_([^\.]+)\.meta$", str(x)) or [None, None])[
                1
            ]
        )
    frame = frame.drop(columns=[c for c in ("time", "device") if c in frame]).dropna(
        subset=["sample_id"]
    )
    return MetadataCatalog(frame, "sample_id")


class IoTDBSignalStore(SignalStore):
    def __init__(self, config: IoTDBConfig, metadata: MetadataCatalog):
        self.config, self.metadata, self.connection = (
            config,
            metadata,
            IoTDBSession(config),
        )

    @property
    def session(self):
        return self.connection.open()

    def _record_device(self, sample_id):
        record = self.metadata.get(sample_id)
        return record, IoTDBPathCodec.signal_device(self.config, record)

    def shape(self, sample_id):
        record = self.metadata.get(sample_id)
        if record.sample_length is None or record.channels is None:
            raise ValueError("IoTDB metadata lacks sample_length/channels")
        return record.sample_length, record.channels

    def contains(self, sample_id):
        _, device = self._record_device(sample_id)
        return bool(self.session.check_time_series_exists(f"{device}.ch_0"))

    def list_ids(self) -> Iterable[str]:
        return tuple(self.metadata.keys())

    def read(self, sample_id, start=0, end=None, channels=None, step=1):
        if int(step) <= 0:
            raise ValueError("step must be positive")
        _, device = self._record_device(sample_id)
        length, count = self.shape(sample_id)
        selected = (
            list(range(count)) if channels is None else [int(c) for c in channels]
        )
        if not selected or any(c < 0 or c >= count for c in selected):
            raise IndexError("Invalid channel selection")
        start = int(start)
        end = length if end is None else min(int(end), length)
        if start < 0 or end < start or start > length:
            raise ValueError("Expected 0 <= start <= end <= length")
        measurements = [f"ch_{c}" for c in selected]
        result = self.session.execute_query_statement(
            f"SELECT {', '.join(measurements)} FROM {device} WHERE time >= {start} AND time < {end}"
        )
        try:
            frame = result.todf()
        finally:
            close = getattr(result, "close_operation_handle", None)
            if callable(close):
                close()
        columns = [
            next(c for c in frame.columns if str(c) == m or str(c).endswith("." + m))
            for m in measurements
        ]
        return frame[columns].to_numpy()[::step]

    def close(self):
        self.connection.close()


class IoTDBImporter:
    SCHEMA = (
        ("sample_id", "TEXT"),
        ("dataset_id", "TEXT"),
        ("name", "TEXT"),
        ("file", "TEXT"),
        ("visible", "BOOLEAN"),
        ("label", "TEXT"),
        ("fault_level", "TEXT"),
        ("rul_label", "TEXT"),
        ("domain_id", "TEXT"),
        ("sample_rate", "DOUBLE"),
        ("sample_length", "INT64"),
        ("channels", "INT32"),
        ("fault_diagnosis", "BOOLEAN"),
        ("anomaly_detection", "BOOLEAN"),
        ("remaining_life", "BOOLEAN"),
    )

    def __init__(self, config):
        self.config, self.connection = config, IoTDBSession(config)

    @property
    def session(self):
        return self.connection.open()

    def ensure_database(self):
        try:
            self.session.execute_non_query_statement(
                f"CREATE DATABASE {self.config.root}"
            )
        except Exception as exc:
            if "exist" not in str(exc).lower() and "already" not in str(exc).lower():
                try:
                    self.session.set_storage_group(self.config.root)
                except Exception as fallback:
                    if (
                        "exist" not in str(fallback).lower()
                        and "already" not in str(fallback).lower()
                    ):
                        raise exc

    def import_sample(self, repository: PHMDataRepository, sample_id, chunk_size=10000):
        if int(chunk_size) <= 0:
            raise ValueError("chunk_size must be positive")
        validation = repository.validate_sample(sample_id)
        if not validation["valid"]:
            raise ValueError(validation["errors"])
        self.ensure_database()
        record = repository.metadata.get(sample_id)
        shape = repository.signals.shape(sample_id)
        length = int(shape[0])
        channels = 1 if len(shape) == 1 else int(shape[1])
        device = IoTDBPathCodec.signal_device(self.config, record)
        self._ensure_signal(device, channels)
        self._write_metadata(record)
        _, Types, _, _, Tablet = _imports()
        measurements = [f"ch_{i}" for i in range(channels)]
        chunks = 0
        for start in range(0, length, chunk_size):
            end = min(start + chunk_size, length)
            matrix = np.asarray(repository.signals.read(sample_id, start, end))
            if matrix.ndim == 1:
                matrix = matrix[:, None]
            while matrix.ndim > 2 and matrix.shape[-1] == 1:
                matrix = np.squeeze(matrix, -1)
            if matrix.ndim != 2 or matrix.shape[1] != channels:
                raise ValueError(f"Invalid signal shape {matrix.shape}")
            tablet = Tablet(
                device,
                measurements,
                [Types.DOUBLE] * channels,
                [np.asarray(matrix[:, i], dtype=np.float64) for i in range(channels)],
                np.arange(start, end, dtype=np.int64),
            )
            self.session.insert_aligned_tablet(tablet)
            chunks += 1
        return {
            "sample_id": str(sample_id),
            "device": device,
            "length": length,
            "channels": channels,
            "chunks": chunks,
        }

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

    def _ensure_signal(self, device, channels):
        _, Types, Enc, Comp, _ = _imports()
        names = [f"ch_{i}" for i in range(channels)]
        missing = [
            n
            for n in names
            if not self.session.check_time_series_exists(f"{device}.{n}")
        ]
        if missing:
            self.session.create_aligned_time_series(
                device,
                missing,
                [Types.DOUBLE] * len(missing),
                [Enc.GORILLA] * len(missing),
                [Comp.SNAPPY] * len(missing),
            )

    def _write_metadata(self, record):
        _, Types, Enc, Comp, _ = _imports()
        device = IoTDBPathCodec.metadata_device(self.config, record)
        names = [n for n, _ in self.SCHEMA]
        types = [getattr(Types, t) for _, t in self.SCHEMA]
        missing = [
            i
            for i, n in enumerate(names)
            if not self.session.check_time_series_exists(f"{device}.{n}")
        ]
        if missing:
            self.session.create_aligned_time_series(
                device,
                [names[i] for i in missing],
                [types[i] for i in missing],
                [Enc.PLAIN] * len(missing),
                [Comp.SNAPPY] * len(missing),
            )
        values = {
            "sample_id": record.sample_id,
            "dataset_id": _txt(record.dataset_id),
            "name": record.name,
            "file": record.file,
            "visible": record.visible,
            "label": _txt(record.label),
            "fault_level": _txt(record.fault_level),
            "rul_label": _txt(record.rul_label),
            "domain_id": _txt(record.domain_id),
            "sample_rate": record.sample_rate,
            "sample_length": record.sample_length,
            "channels": record.channels,
            "fault_diagnosis": record.fault_diagnosis,
            "anomaly_detection": record.anomaly_detection,
            "remaining_life": record.remaining_life,
        }
        chosen = [
            (n, t, values[n]) for n, t in zip(names, types) if values.get(n) is not None
        ]
        self.session.insert_aligned_record(
            device,
            0,
            [x[0] for x in chosen],
            [x[1] for x in chosen],
            [x[2] for x in chosen],
        )

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def _txt(value):
    value = clean_value(value)
    return None if value is None else str(value)


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
        "metadata_fields": [name for name, _ in IoTDBImporter.SCHEMA],
        "source": dict(source_manifest or {}),
        "sample_ids": repository.metadata.keys(),
        "imported_sample_ids": [str(item["sample_id"]) for item in imported],
        "failed_sample_ids": [str(item["sample_id"]) for item in failed],
    }


def _imports():
    try:
        from iotdb.Session import Session
        from iotdb.utils.IoTDBConstants import Compressor, TSDataType, TSEncoding
        from iotdb.utils.NumpyTablet import NumpyTablet
    except ImportError as exc:
        raise RuntimeError("Install phm-data-factory with its runtime dependencies") from exc
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
