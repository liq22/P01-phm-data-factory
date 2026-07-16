"""Path-independent dataset identity manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

IDENTITY_SCHEMA_VERSION = "phm-data-factory/dataset-identity-v1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _content_entry(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "name": str(value.get("name") or ""),
        "size_bytes": int(value.get("size_bytes") or 0),
        "sha256": str(value.get("sha256") or ""),
    }
    if not result["sha256"]:
        raise ValueError("source manifest entry is missing sha256")
    return result


def identity_projection(
    source_manifest: Mapping[str, Any],
    sample_ids: Sequence[str],
) -> dict[str, Any]:
    """Select stable content fields, excluding paths and deployment details."""

    source = dict(source_manifest)
    metadata = _content_entry(dict(source.get("metadata") or {}))
    signals = dict(source.get("signals") or {})
    if signals.get("kind") == "directory":
        signal_content: dict[str, Any] = {
            "kind": "directory",
            "files": sorted(
                (_content_entry(dict(item)) for item in signals.get("files") or []),
                key=lambda item: (item["name"], item["sha256"]),
            ),
        }
    else:
        signal_content = {"kind": "file", **_content_entry(signals)}
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "metadata": metadata,
        "signals": signal_content,
        "sample_ids": sorted({str(item) for item in sample_ids}),
    }


def build_dataset_identity(
    source_manifest: Mapping[str, Any],
    sample_ids: Sequence[str],
) -> dict[str, Any]:
    projection = identity_projection(source_manifest, sample_ids)
    digest = hashlib.sha256(canonical_json(projection)).hexdigest()
    return {
        **projection,
        "digest_algorithm": "sha256",
        "dataset_digest": f"sha256:{digest}",
    }


def validate_dataset_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    identity = dict(value)
    if identity.get("schema_version") != IDENTITY_SCHEMA_VERSION:
        raise ValueError("unsupported dataset identity schema")
    supplied = str(identity.pop("dataset_digest", ""))
    algorithm = identity.pop("digest_algorithm", None)
    if algorithm != "sha256" or not supplied.startswith("sha256:"):
        raise ValueError("dataset identity must use sha256")
    expected = "sha256:" + hashlib.sha256(canonical_json(identity)).hexdigest()
    if supplied != expected:
        raise ValueError("dataset identity digest mismatch")
    return {**identity, "digest_algorithm": algorithm, "dataset_digest": supplied}


def load_dataset_identity(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if "data_manifest" in raw:
        raw = raw["data_manifest"]
    if "dataset_identity" in raw:
        raw = raw["dataset_identity"]
    if not isinstance(raw, Mapping):
        raise ValueError("dataset identity file must contain a JSON mapping")
    return validate_dataset_identity(raw)
