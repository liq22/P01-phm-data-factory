from __future__ import annotations

import json

from phm_data_factory import API_SCHEMA_VERSION, PACKAGE_VERSION, agent_contract_manifest
from phm_data_factory.agent import AgentDataTools


def test_agent_manifest_is_versioned_read_only_and_json_safe():
    manifest = AgentDataTools.manifest()

    assert manifest["provider"] == "phm-data-factory"
    assert manifest["package_version"] == PACKAGE_VERSION
    assert manifest["version"] == PACKAGE_VERSION
    assert manifest["api_schema_version"] == API_SCHEMA_VERSION
    assert manifest["api_schema_version"].split(".", 1)[0] == "1"
    assert manifest["read_only"] is True
    assert manifest["capabilities"]["bounded_window"] is True
    assert manifest["capabilities"]["window_statistics"] is True
    assert manifest["capabilities"]["stream_cursor"] is False
    assert manifest["capabilities"]["modalities"] == ["continuous_series"]
    assert manifest["dataset_digest"] is None

    json.dumps(manifest, sort_keys=True)


def test_manifest_returns_fresh_nested_values():
    first = agent_contract_manifest()
    first["tools"].append("mutating_test_tool")
    first["capabilities"]["modalities"].append("unsupported_modality")

    second = agent_contract_manifest()
    assert "mutating_test_tool" not in second["tools"]
    assert second["capabilities"]["modalities"] == ["continuous_series"]


def test_package_version_has_single_contract_source():
    manifest = agent_contract_manifest()
    assert PACKAGE_VERSION == "0.1.0"
    assert manifest["package_version"] == PACKAGE_VERSION
