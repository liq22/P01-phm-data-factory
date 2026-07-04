"""CLI-level tests for phm-data-iotdb (check socket probe + import config/env)."""

from __future__ import annotations

import json

import pytest

from phm_data_factory import iotdb


def test_check_returns_3_when_port_closed(capsys, monkeypatch):
    monkeypatch.delenv("PHM_DATA_CONFIG", raising=False)
    monkeypatch.setattr(iotdb, "_probe_socket", lambda *a, **k: False)
    code = iotdb.main(["check"])
    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["rpc_port_open"] is False
    assert payload["connected"] is False
    assert "error" in payload


def test_check_returns_0_when_connected(capsys, monkeypatch):
    monkeypatch.delenv("PHM_DATA_CONFIG", raising=False)
    monkeypatch.setattr(iotdb, "_probe_socket", lambda *a, **k: True)

    class _FakeSession:
        def __init__(self, config):
            self.config = config

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(iotdb, "IoTDBSession", _FakeSession)
    code = iotdb.main(["check"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rpc_port_open"] is True
    assert payload["connected"] is True


def test_check_returns_3_when_session_fails_but_port_open(capsys, monkeypatch):
    """Port open + Session auth failure → connected False, return 3, error kept."""
    monkeypatch.delenv("PHM_DATA_CONFIG", raising=False)
    monkeypatch.setattr(iotdb, "_probe_socket", lambda *a, **k: True)

    class _BoomSession:
        def __init__(self, config):
            self.config = config

        def __enter__(self):
            raise RuntimeError("auth denied")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(iotdb, "IoTDBSession", _BoomSession)
    code = iotdb.main(["check"])
    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["rpc_port_open"] is True
    assert payload["connected"] is False
    assert "session failed" in payload["error"]


def test_import_errors_without_metadata_and_signals(capsys, monkeypatch):
    monkeypatch.delenv("PHM_DATA_CONFIG", raising=False)
    code = iotdb.main(["import", "--host", "127.0.0.1"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "requires" in payload["message"]


def test_resolve_iotdb_config_reads_phm_data_config(monkeypatch, tmp_path):
    cfg = tmp_path / "phm-data.yaml"
    cfg.write_text(
        "backend: local\n"
        f"metadata_path: {tmp_path / 'm.xlsx'}\n"
        f"signal_path: {tmp_path}\n"
        "iotdb:\n"
        "  host: db.example\n"
        "  port: 9999\n"
        "  root: root.x\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHM_DATA_CONFIG", str(cfg))

    class _Args:
        config = None
        host = "127.0.0.1"
        port = 6667
        user = "root"
        password = "root"
        root = "root.vibench"

    db, rc = iotdb._resolve_iotdb_config(_Args())
    assert db.host == "db.example"
    assert db.port == 9999
    assert db.root == "root.x"
    assert rc is not None
    assert str(rc.metadata_path).endswith("m.xlsx")
