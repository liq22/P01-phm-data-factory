#!/usr/bin/env python3
"""按数据集过滤导入 IoTDB（跨机可复用：数据路径全部走 config，不硬编码）。

用法示例：
  # 导除无文件的数据集外的全部（推荐）
  python scripts/import_datasets.py --config config/phm-data.yaml \\
      --all-except RM_005_Ottawa23,RM_006_THU,RM_007_MFPT \\
      --skip-existing --continue-on-error --report import-report.json

  # 只导指定数据集
  python scripts/import_datasets.py --config config/phm-data.yaml \\
      --datasets RM_016_JNU,RM_017_Ottawa19 --report import-report.json

数据目录变化时，只需改 config/phm-data.yaml 的 metadata_path / signal_path。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="按数据集过滤导入 IoTDB")
    p.add_argument("--config", required=True, help="RepositoryConfig yaml（含 metadata_path/signal_path/iotdb）")
    p.add_argument("--datasets", help="逗号分隔的 dataset name 列表（只导这些）")
    p.add_argument("--all-except", dest="all_except", help="逗号分隔的 dataset name 列表（排除这些，导其余）")
    p.add_argument("--skip-existing", action="store_true", help="跳过 IoTDB 已有 sample（断点续传，一次 SELECT 拿已导集合）")
    p.add_argument("--continue-on-error", action="store_true", help="失败样本跳过继续（写入 failed）")
    p.add_argument("--chunk-size", type=int, default=10000)
    p.add_argument("--report", help="写入 import-report JSON 路径")
    args = p.parse_args(argv)

    from phm_data_factory import RepositoryConfig, PHMDataRepository
    from phm_data_factory.iotdb import (
        IoTDBConfig,
        IoTDBImporter,
        build_source_manifest,
        load_metadata_from_iotdb,
    )

    config = RepositoryConfig.from_file(args.config)
    if not config.metadata_path or not config.signal_path:
        print("--config 必须含 metadata_path 与 signal_path（导入源路径）", file=sys.stderr)
        return 2

    repo = PHMDataRepository.from_local(config.metadata_path, config.signal_path)
    catalog = repo.metadata

    # 1. 按数据集过滤 sample_ids（按 metadata 的 name 列）
    all_names = [d["name"] for d in catalog.list_datasets() if d.get("name")]
    if args.datasets:
        include = {n.strip() for n in args.datasets.split(",") if n.strip()}
    elif args.all_except:
        exclude = {n.strip() for n in args.all_except.split(",") if n.strip()}
        include = set(all_names) - exclude
    else:
        include = set(all_names)
    unknown = include - set(all_names)
    if unknown:
        print(f"警告：数据集名不在 metadata：{unknown}", file=sys.stderr)

    sample_ids: list[str] = []
    for name in sorted(include):
        for r in catalog.search({"name": name}, limit=None):
            sample_ids.append(r.sample_id)
    print(f"选定 {len(sample_ids)} 样本（来自 {len(include)} 数据集）", file=sys.stderr)

    # 2. 断点续传：剔除 IoTDB 已导
    db = IoTDBConfig.from_mapping(config.iotdb) if config.iotdb else IoTDBConfig()
    if args.skip_existing:
        try:
            existing = set(load_metadata_from_iotdb(db).keys())
            before = len(sample_ids)
            sample_ids = [sid for sid in sample_ids if sid not in existing]
            print(f"断点续传：跳过 {before - len(sample_ids)} 已导，剩 {len(sample_ids)}", file=sys.stderr)
        except Exception as exc:
            print(f"警告：读已导集合失败（{exc}），不跳过", file=sys.stderr)

    if not sample_ids:
        print("无样本可导", file=sys.stderr)
        return 0

    # 3. 导入（串行；Session 非 thread-safe，勿并发共享）
    source_manifest = build_source_manifest(config.metadata_path, config.signal_path)
    with IoTDBImporter(db) as importer:
        result = importer.import_repository(
            repo,
            sample_ids=sample_ids,
            chunk_size=args.chunk_size,
            visible_only=False,
            continue_on_error=args.continue_on_error,
            source_manifest=source_manifest,
        )

    if args.report:
        Path(args.report).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "imported_count": result["imported_count"],
        "failed_count": result["failed_count"],
        "root": result["root"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
