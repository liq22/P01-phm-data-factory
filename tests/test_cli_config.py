from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

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


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".yaml", "- local\n- iotdb\n"),
        (".json", '["local", "iotdb"]'),
    ],
)
def test_config_file_rejects_non_mapping_root(
    tmp_path: Path, suffix: str, content: str
):
    config_path = tmp_path / f"invalid{suffix}"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="top-level mapping"):
        RepositoryConfig.from_file(config_path)


def test_config_rejects_non_mapping_iotdb_section():
    with pytest.raises(ValueError, match="iotdb must be a mapping"):
        RepositoryConfig.from_mapping({"backend": "iotdb", "iotdb": ["host"]})


def test_environment_backend_is_case_insensitive(monkeypatch):
    monkeypatch.delenv("PHM_DATA_CONFIG", raising=False)
    monkeypatch.setenv("PHM_DATA_BACKEND", "IOTDB")
    monkeypatch.setenv("IOTDB_HOST", "iotdb.example")

    config = RepositoryConfig.from_environment()

    assert config.backend == "iotdb"
    assert config.iotdb["host"] == "iotdb.example"


def test_explicit_config_has_priority_over_environment(
    local_data, monkeypatch, tmp_path: Path, capsys
):
    metadata, signals = local_data
    env_config = tmp_path / "env.yaml"
    env_config.write_text(
        "backend: local\n"
        "metadata_path: missing-metadata.csv\n"
        "signal_path: missing-signals\n",
        encoding="utf-8",
    )
    explicit_config = tmp_path / "explicit.yaml"
    explicit_config.write_text(
        "backend: local\n"
        f"metadata_path: {metadata}\n"
        f"signal_path: {signals}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PHM_DATA_CONFIG", str(env_config))

    code = main(["--config", str(explicit_config), "summary"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["samples"] == 2


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


def test_cli_phm_data_config_env_drives_query(
    local_data, monkeypatch, tmp_path: Path, capsys
):
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
