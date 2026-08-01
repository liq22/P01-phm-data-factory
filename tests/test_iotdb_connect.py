"""connect() one-liner entry point: config-type handling + overrides + local e2e."""
from __future__ import annotations

from pathlib import Path

import pytest

import phm_data_factory.config as cfg_mod
from phm_data_factory import PHMDataRepository, connect


def test_connect_local_mapping_end_to_end(local_data):
    metadata_path, h5_path = local_data
    repo = connect(
        {
            "backend": "local",
            "metadata_path": str(metadata_path),
            "signal_path": str(h5_path),
        }
    )
    try:
        assert isinstance(repo, PHMDataRepository)
        assert repo.read_signal(1).shape == (12, 2)
    finally:
        repo.close()


def _capture_build(monkeypatch):
    """Redirect build_repository to capture the resolved RepositoryConfig."""
    seen = []
    monkeypatch.setattr(
        cfg_mod,
        "build_repository",
        lambda rc: seen.append(rc) or object(),  # return a sentinel; we only inspect rc
    )
    return seen


def test_connect_accepts_repository_config(monkeypatch):
    seen = _capture_build(monkeypatch)
    from phm_data_factory import RepositoryConfig

    rc = RepositoryConfig.from_mapping({"backend": "iotdb", "iotdb": {"host": "h"}})
    connect(rc)
    assert seen[-1] is rc


def test_connect_accepts_mapping(monkeypatch):
    seen = _capture_build(monkeypatch)
    connect({"backend": "iotdb", "iotdb": {"host": "h", "port": 7000}})
    assert seen[-1].backend == "iotdb"
    assert seen[-1].iotdb["host"] == "h"


def test_connect_accepts_yaml_path(monkeypatch, tmp_path):
    seen = _capture_build(monkeypatch)
    cfg = tmp_path / "phm-data.yaml"
    cfg.write_text(
        "backend: iotdb\niotdb:\n  host: fromfile\n  port: 6667\n", encoding="utf-8"
    )
    connect(str(cfg))
    assert seen[-1].iotdb["host"] == "fromfile"


def test_connect_none_reads_env(monkeypatch, tmp_path):
    seen = _capture_build(monkeypatch)
    cfg = tmp_path / "phm-data.yaml"
    cfg.write_text("backend: iotdb\niotdb:\n  host: envhost\n", encoding="utf-8")
    monkeypatch.setenv("PHM_DATA_CONFIG", str(cfg))
    connect(None)
    assert seen[-1].iotdb["host"] == "envhost"


def test_connect_overrides_merge_into_iotdb(monkeypatch):
    seen = _capture_build(monkeypatch)
    connect({"backend": "iotdb", "iotdb": {"host": "orig", "port": 6667}}, host="overridden", fetch_size=999)
    assert seen[-1].iotdb["host"] == "overridden"  # override wins
    assert seen[-1].iotdb["port"] == 6667  # original preserved
    assert seen[-1].iotdb["fetch_size"] == 999  # override added


def test_connect_returns_repository_not_store(local_data):
    """connect must return a PHMDataRepository (same abstraction for local/iotdb),
    not a bare store."""
    metadata_path, h5_path = local_data
    repo = connect(
        {
            "backend": "local",
            "metadata_path": str(metadata_path),
            "signal_path": str(h5_path),
        }
    )
    try:
        assert isinstance(repo, PHMDataRepository)
    finally:
        repo.close()
