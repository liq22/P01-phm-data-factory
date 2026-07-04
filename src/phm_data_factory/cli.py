"""JSON CLI for people and shell-based agents."""

from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any, Sequence
from .agent import AgentDataTools
from .config import RepositoryConfig, build_repository, env_config_present


def parser():
    p = argparse.ArgumentParser(prog="phm-data")
    p.add_argument("--config")
    p.add_argument("--metadata")
    p.add_argument("--signals")
    p.add_argument("--backend", choices=("local", "iotdb"), default="iotdb")
    p.add_argument("--default-max-points", type=int, default=4096)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=6667)
    p.add_argument("--user", default="root")
    p.add_argument("--password", default="root")
    p.add_argument("--root", default="root.vibench")
    p.add_argument("--fetch-size", type=int, default=5000)
    p.add_argument("--zone-id", default="UTC")
    p.add_argument("--compact", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("summary")
    sub.add_parser("datasets")
    sub.add_parser("manifest")
    s = sub.add_parser("search")
    s.add_argument("--filter", action="append", default=[])
    s.add_argument("--task")
    s.add_argument("--visible-only", action="store_true")
    s.add_argument("--limit", type=int, default=50)
    m = sub.add_parser("metadata")
    m.add_argument("sample_id")
    for name in ("window", "stats"):
        q = sub.add_parser(name)
        q.add_argument("sample_id")
        q.add_argument("--start", type=int, default=0)
        q.add_argument("--end", type=int)
        q.add_argument("--channels", type=lambda x: [int(v) for v in x.split(",")])
        q.add_argument(
            "--max-points", type=int, default=100000 if name == "stats" else None
        )
    v = sub.add_parser("validate")
    v.add_argument("sample_id")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.config:
            config = RepositoryConfig.from_file(args.config)
        elif env_config_present():
            config = RepositoryConfig.from_environment()
        else:
            config = RepositoryConfig.from_mapping(
                {
                    "backend": args.backend,
                    "metadata_path": args.metadata,
                    "signal_path": args.signals,
                    "default_max_points": args.default_max_points,
                    "iotdb": {
                        "host": args.host,
                        "port": args.port,
                        "user": args.user,
                        "password": args.password,
                        "root": args.root,
                        "fetch_size": args.fetch_size,
                        "zone_id": args.zone_id,
                    },
                },
                Path.cwd(),
            )
        with build_repository(config) as repo:
            tools = AgentDataTools(repo, config.default_max_points)
            if args.command == "summary":
                result = tools.repository_summary()
            elif args.command == "datasets":
                result = tools.list_datasets()
            elif args.command == "manifest":
                result = tools.manifest()
            elif args.command == "search":
                filters = {}
                for item in args.filter:
                    key, raw = item.split("=", 1)
                    try:
                        filters[key] = json.loads(raw)
                    except json.JSONDecodeError:
                        filters[key] = raw
                result = tools.search_samples(
                    task=args.task,
                    visible_only=args.visible_only,
                    limit=args.limit,
                    extra_filters=filters,
                )
            elif args.command == "metadata":
                result = tools.get_sample_metadata(args.sample_id)
            elif args.command == "window":
                result = tools.get_signal_window(
                    args.sample_id, args.start, args.end, args.channels, args.max_points
                )
            elif args.command == "stats":
                result = tools.get_signal_statistics(
                    args.sample_id, args.start, args.end, args.channels, args.max_points
                )
            else:
                result = tools.validate_sample(args.sample_id)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":") if args.compact else None,
                indent=None if args.compact else 2,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
