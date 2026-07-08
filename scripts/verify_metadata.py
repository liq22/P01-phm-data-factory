#!/usr/bin/env python3
"""核对 source metadata.xlsx 与 IoTDB 读回的 metadata 一致性。

对比维度：
  1. sample_id 集合 diff（only_in_source / only_in_iotdb / common）
  2. 15 个 SCHEMA 字段逐值对比（容忍 _txt/as_bool 类型转换 + 源空⇔IoTDB 无点）
  3. IoTDB 实际有数据的字段列 vs SCHEMA（捕获静默字段丢失）

用法：
  python scripts/verify_metadata.py --config config/phm-data.yaml [--report verify-report.json]
  python scripts/verify_metadata.py --config config/phm-data.yaml --datasets RM_016_JNU
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="核对 source vs IoTDB metadata")
    p.add_argument("--config", required=True, help="RepositoryConfig yaml（含 metadata_path + iotdb）")
    p.add_argument("--datasets", help="只核对指定数据集（逗号分隔 name）；默认全部")
    p.add_argument("--report", help="写入 JSON 报告路径")
    args = p.parse_args(argv)

    from phm_data_factory import MetadataCatalog, RepositoryConfig
    from phm_data_factory.iotdb import IoTDBConfig, IoTDBImporter, load_metadata_from_iotdb
    from phm_data_factory.models import as_bool, clean_value

    schema = IoTDBImporter.SCHEMA  # [(name, iotdb_type)]
    fields = [n for n, _ in schema]
    text_fields = {n for n, t in schema if t == "TEXT"}
    bool_fields = {n for n, t in schema if t == "BOOLEAN"}
    num_fields = {n for n, t in schema if t in ("DOUBLE", "INT64", "INT32")}

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
                f = float(value)
                return int(f) if f.is_integer() else f
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

    src_keys = set(source.keys())
    db_keys = set(iotdb.keys())

    if args.datasets:
        names = {n.strip() for n in args.datasets.split(",") if n.strip()}

        def _name(cat, sid):
            try:
                return cat.get(sid).name
            except Exception:
                return None

        src_keys = {sid for sid in src_keys if _name(source, sid) in names}
        db_keys = {sid for sid in db_keys if _name(iotdb, sid) in names}

    only_source = sorted(src_keys - db_keys)
    only_iotdb = sorted(db_keys - src_keys)
    common = sorted(src_keys & db_keys)

    field_diffs = []
    for sid in common:
        src_rec = source.get(sid)
        db_rec = iotdb.get(sid)
        for f in fields:
            sv = normalize(f, getattr(src_rec, f, None))
            dv = normalize(f, getattr(db_rec, f, None))
            if sv != dv:
                field_diffs.append({"sample_id": sid, "field": f, "source": sv, "iotdb": dv})

    db_cols: set[str] = set()
    for sid in common:
        for k, v in iotdb.raw(sid).items():
            if v is not None:
                db_cols.add(k)
    missing_columns = sorted(set(fields) - db_cols)

    report = {
        "scope": {"datasets": args.datasets or "(all)", "common": len(common)},
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
        "note": "SCHEMA 15 字段全应存在；description/sample_type/label_description/rul_label_description/domain_description 不在 SCHEMA（设计性不导）",
    }
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "common": len(common),
        "only_in_source": len(only_source),
        "only_in_iotdb": len(only_iotdb),
        "field_diffs": len(field_diffs),
        "missing_columns_in_iotdb": missing_columns,
    }, ensure_ascii=False, indent=2))
    # only_in_source=0（全导进）+ field_diffs=0（值一致）= 通过
    ok = len(only_source) == 0 and len(field_diffs) == 0
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
