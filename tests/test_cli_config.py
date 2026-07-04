from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from phm_data_factory.cli import main
from phm_data_factory.config import RepositoryConfig


def test_cli_summary(local_data, capsys):
    metadata, signals = local_data
    code = main(
        [
            "--backend",
            "local",
            "--metadata",
            str(metadata),
            "--signals",
            str(signals),
            "summary",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["samples"] == 2


def test_yaml_config_resolves_relative_paths(local_data, tmp_path: Path):
    metadata, signals = local_data
    config_path = tmp_path / "phm-data.yaml"
    config_path.write_text(
        "backend: local\n"
        f"metadata_path: {metadata.name}\n"
        f"signal_path: {signals.name}\n",
        encoding="utf-8",
    )
    config = RepositoryConfig.from_file(config_path)
    assert config.metadata_path == metadata.resolve()
    assert config.signal_path == signals.resolve()


def test_iotdb_config_can_load_catalog_from_database():
    config = RepositoryConfig.from_mapping(
        {"backend": "iotdb", "iotdb": {"root": "root.test"}}
    )
    assert config.metadata_path is None
    assert config.iotdb["root"] == "root.test"


def test_default_config_is_iotdb():
    config = RepositoryConfig.from_mapping({})
    assert config.backend == "iotdb"
    assert config.metadata_path is None
    assert config.signal_path is None


def test_top_level_import_does_not_load_h5py():
    env = dict(os.environ)
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = (
        source_root
        if not env.get("PYTHONPATH")
        else os.pathsep.join([source_root, env["PYTHONPATH"]])
    )
    code = (
        "import sys;"
        "import phm_data_factory;"
        "raise SystemExit(1 if 'h5py' in sys.modules else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], env=env, check=False)
    assert result.returncode == 0


def test_env_config_present_only_triggers_on_phm_data_config(monkeypatch):
    """Scattered IOTDB_* must NOT activate the env chain on the CLI (regression guard)."""
    from phm_data_factory.config import env_config_present

    monkeypatch.delenv("PHM_DATA_CONFIG", raising=False)
    monkeypatch.setenv("IOTDB_HOST", "somewhere.example")
    monkeypatch.setenv("IOTDB_PORT", "6667")
    assert env_config_present() is False  # IOTDB_* alone must not trigger
    monkeypatch.setenv("PHM_DATA_CONFIG", "x.yaml")
    assert env_config_present() is True


def test_cli_phm_data_config_env_drives_query(local_data, monkeypatch, tmp_path: Path, capsys):
    """PHM_DATA_CONFIG (no --config, no CLI flags) drives the whole query."""
    metadata, signals = local_data
    cfg = tmp_path / "phm-data.yaml"
    cfg.write_text(
        "backend: local\n"
        f"metadata_path: {metadata}\n"
        f"signal_path: {signals}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHM_DATA_CONFIG", str(cfg))
    code = main(["summary"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["samples"] == 2
