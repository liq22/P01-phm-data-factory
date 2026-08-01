from __future__ import annotations

import json

import pytest

from phm_data_factory import iotdb


def test_source_manifest_command_writes_reusable_json(local_data, tmp_path, capsys):
    metadata, signals = local_data
    output = tmp_path / "source-manifest.json"
    code = iotdb.main(
        [
            "source-manifest",
            "--metadata",
            str(metadata),
            "--signals",
            str(signals),
            "--output",
            str(output),
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["sha256"]
    assert payload["signals"]["sha256"]
    assert json.loads(capsys.readouterr().out) == payload


def test_import_skip_source_manifest_is_explicit(local_data, monkeypatch, capsys):
    metadata, signals = local_data
    captured = {}

    class Importer:
        def __init__(self, config):
            del config

        def __enter__(self):
            return self

        def __exit__(self, *args):
            del args

        def import_repository(self, repo, *args, **kwargs):
            del repo, args
            captured.update(kwargs)
            return {
                "imported_count": 1,
                "failed_count": 0,
                "root": "root.vibench",
                "data_manifest": {
                    "source_manifest_mode": kwargs["source_manifest_mode"],
                    "provenance_complete": False,
                    "dataset_identity": None,
                    "dataset_digest": None,
                },
            }

    monkeypatch.setattr(iotdb, "IoTDBImporter", Importer)
    monkeypatch.setattr(
        iotdb,
        "build_source_manifest",
        lambda *args: pytest.fail(f"unexpected source hashing: {args}"),
    )
    code = iotdb.main(
        [
            "import",
            "--metadata",
            str(metadata),
            "--signals",
            str(signals),
            "--sample-id",
            "1",
            "--skip-source-manifest",
        ]
    )
    assert code == 0
    assert captured["source_manifest"] is None
    assert captured["source_manifest_mode"] == "skipped"
    payload = json.loads(capsys.readouterr().out)
    assert payload["data_manifest"]["dataset_digest"] is None


def test_import_manifest_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        iotdb.main(
            [
                "import",
                "--metadata",
                "metadata.csv",
                "--signals",
                "signals.h5",
                "--source-manifest",
                "manifest.json",
                "--skip-source-manifest",
            ]
        )
    assert exc.value.code == 2
