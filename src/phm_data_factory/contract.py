"""Versioned public contract for benchmark and agent consumers.

The manifest describes capabilities that are implemented today. Future signal
modalities or streaming APIs must increment the schema and add compatibility
tests before being advertised here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PACKAGE_VERSION = "0.1.0"
API_SCHEMA_VERSION = "1.0.0"
CAPABILITY_SCHEMA_VERSION = "1.0.0"

_AGENT_TOOLS = (
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


def agent_contract_manifest() -> dict[str, Any]:
    """Return a fresh JSON-safe manifest for read-only agent consumers."""

    return {
        "provider": "phm-data-factory",
        "name": "phm-data-factory",
        "package_version": PACKAGE_VERSION,
        "version": PACKAGE_VERSION,
        "api_schema_version": API_SCHEMA_VERSION,
        "capability_schema_version": CAPABILITY_SCHEMA_VERSION,
        "read_only": True,
        "backend_kind": "runtime_selected",
        "dataset_digest": None,
        "tools": list(_AGENT_TOOLS),
        "capabilities": deepcopy(_CAPABILITIES),
        "compatibility": {
            "schema_rule": "same_major_version",
            "pre_1_0_api": True,
            "deprecation_notice": "at_least_one_minor_release_when_feasible",
        },
    }
