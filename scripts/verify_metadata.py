#!/usr/bin/env python3
"""Verify source metadata against the metadata committed in IoTDB."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="核对 source vs IoTDB metadata")
    parser.add_argument(
        "--config", required=True, help="RepositoryConfig yaml（含 metadata_path + iotdb）"
    )
    parser.add_argument("--datasets", help="只核对指定数据集（逗号分隔 name）；默认全部")
    parser.add_argument("--report", help="写入 JSON 报告路径")
    args = parser.parse_args(argv)

    from phm_data_factory import MetadataCatalog, RepositoryConfig
    from phm_data_factory.iotdb import (
        IoTDBConfig,
        IoTDBImporter,
        load_metadata_from_iotdb,
    )
    from phm_data_factory.models import as_bool, clean_value

    schema = IoTDBImporter.SCHEMA
    fields = [name for name, _ in schema]
    text_fields = {name for name, data_type in schema if data_type == "TEXT"}
    bool_fields = {name for name, data_type in schema if data_type == "BOOLEAN"}
    num_fields = {
        name
        for name, data_type in schema
        if data_type in ("DOUBLE", "INT64", "INT32")
    }

    def normalize(field: str, value):
        value = clean_value(value)
        if value is None:
            return None
        if field in text_fields:
            return str(value)
        if field in bool_fields:
            return as_bool(value)
        if field in num_fields:
            try:
                number = float(value)
                return int(number) if number.is_integer() else number
            except (TypeError, ValueError):
                return None
        return value

    config = RepositoryConfig.from_file(args.config)
    if not config.metadata_path:
        print("--config 必须含 metadata_path（source xlsx）", file=sys.stderr)
        return 2
    db = IoTDBConfig.from_mapping(config.iotdb) if config.iotdb else IoTDBConfig()

    print("加载 source metadata...", file=sys.stderr)
    source = MetadataCatalog.from_file(config.metadata_path)
    print("加载 IoTDB metadata...", file=sys.stderr)
    iotdb = load_metadata_from_iotdb(db)

    source_keys = set(source.keys())
    iotdb_keys = set(iotdb.keys())
    if args.datasets:
        names = {name.strip() for name in args.datasets.split(",") if name.strip()}

        def dataset_name(catalog, sample_id):
            try:
                return catalog.get(sample_id).name
            except Exception:
                return None

        source_keys = {
            sample_id
            for sample_id in source_keys
            if dataset_name(source, sample_id) in names
        }
        iotdb_keys = {
            sample_id
            for sample_id in iotdb_keys
            if dataset_name(iotdb, sample_id) in names
        }

    only_source = sorted(source_keys - iotdb_keys)
    only_iotdb = sorted(iotdb_keys - source_keys)
    common = sorted(source_keys & iotdb_keys)

    field_diffs = []
    source_non_null: set[str] = set()
    for sample_id in common:
        source_record = source.get(sample_id)
        iotdb_record = iotdb.get(sample_id)
        for field in fields:
            source_value = normalize(field, getattr(source_record, field, None))
            iotdb_value = normalize(field, getattr(iotdb_record, field, None))
            if source_value is not None:
                source_non_null.add(field)
            if source_value != iotdb_value:
                field_diffs.append(
                    {
                        "sample_id": sample_id,
                        "field": field,
                        "source": source_value,
                        "iotdb": iotdb_value,
                    }
                )

    iotdb_non_null: set[str] = set()
    for sample_id in common:
        for key, value in iotdb.raw(sample_id).items():
            if value is not None:
                iotdb_non_null.add(key)
    # A schema field that is null in every source row does not need a data point.
    missing_columns = sorted(source_non_null - iotdb_non_null)

    report = {
        "scope": {"datasets": args.datasets or "(all)", "common": len(common)},
        "schema_fields": fields,
        "sample_id_diff": {
            "only_in_source_count": len(only_source),
            "only_in_source_sample": only_source[:20],
            "only_in_iotdb_count": len(only_iotdb),
            "only_in_iotdb_sample": only_iotdb[:20],
            "common_count": len(common),
        },
        "field_diffs_count": len(field_diffs),
        "field_diffs_sample": field_diffs[:20],
        "missing_columns_in_iotdb": missing_columns,
        "note": "Only schema fields with at least one non-null source value are required.",
    }
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "common": len(common),
                "only_in_source": len(only_source),
                "only_in_iotdb": len(only_iotdb),
                "field_diffs": len(field_diffs),
                "missing_columns_in_iotdb": missing_columns,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    ok = len(only_source) == 0 and len(field_diffs) == 0
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
