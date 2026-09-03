"""Versioned public contract for benchmark and agent consumers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PACKAGE_VERSION = "0.2.1"
API_SCHEMA_VERSION = "1.0.0"
CAPABILITY_SCHEMA_VERSION = "1.0.0"

AGENT_TOOLS = (
    "repository_summary",
    "list_datasets",
    "search_samples",
    "get_sample_metadata",
    "get_signal_window",
    "get_signal_statistics",
    "validate_sample",
)

_CAPABILITIES: dict[str, Any] = {
    "search_samples": True,
    "describe_sample": True,
    "bounded_window": True,
    "window_statistics": True,
    "stream_cursor": False,
    "batch_window": False,
    "modalities": ["continuous_series"],
    "timestamp_bases": ["sample_index"],
    "label_visibility_policy": "legacy_metadata_surface_to_be_versioned",
}


def agent_contract_manifest(
    *,
    backend_kind: str = "runtime_selected",
    dataset_digest: str | None = None,
    label_visibility_policy: str | None = None,
) -> dict[str, Any]:
    """Return a fresh, bounded, JSON-safe read-only Agent manifest."""

    capabilities = deepcopy(_CAPABILITIES)
    if label_visibility_policy is not None:
        capabilities["label_visibility_policy"] = label_visibility_policy
    return {
        "provider": "phm-data-factory",
        "name": "phm-data-factory",
        "package_version": PACKAGE_VERSION,
        "version": PACKAGE_VERSION,
        "api_schema_version": API_SCHEMA_VERSION,
        "capability_schema_version": CAPABILITY_SCHEMA_VERSION,
        "api_version": "0.2",  # deprecated compatibility alias
        "read_only": True,
        "backend_kind": backend_kind,
        "dataset_digest": dataset_digest,
        "tools": list(AGENT_TOOLS),
        "capabilities": capabilities,
        "compatibility": {
            "schema_rule": "same_major_version",
            "deprecated_aliases": ["api_version"],
        },
    }
