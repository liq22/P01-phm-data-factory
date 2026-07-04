"""Read-only MCP server for local agents."""

from __future__ import annotations
import argparse, atexit
from typing import Sequence
from .agent import AgentDataTools
from .config import RepositoryConfig, build_repository, env_config_present


def create_server(config: RepositoryConfig):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install phm-data-factory[agent]") from exc
    repository = build_repository(config)
    tools = AgentDataTools(repository, config.default_max_points)
    mcp = FastMCP("PHM Data Factory")

    @mcp.tool()
    def repository_summary() -> dict:
        return tools.repository_summary()

    @mcp.tool()
    def list_datasets() -> list[dict]:
        return tools.list_datasets()

    @mcp.tool()
    def search_samples(
        dataset_id: str | None = None,
        name: str | None = None,
        label: str | None = None,
        domain_id: str | None = None,
        task: str | None = None,
        visible_only: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        return tools.search_samples(
            dataset_id, name, label, domain_id, task, visible_only, limit
        )

    @mcp.tool()
    def get_sample_metadata(sample_id: str) -> dict:
        return tools.get_sample_metadata(sample_id)

    @mcp.tool()
    def get_signal_window(
        sample_id: str,
        start: int = 0,
        end: int | None = None,
        channels: list[int] | None = None,
        max_points: int | None = None,
    ) -> dict:
        return tools.get_signal_window(sample_id, start, end, channels, max_points)

    @mcp.tool()
    def get_signal_statistics(
        sample_id: str,
        start: int = 0,
        end: int | None = None,
        channels: list[int] | None = None,
        max_points: int = 100000,
    ) -> dict:
        return tools.get_signal_statistics(sample_id, start, end, channels, max_points)

    @mcp.tool()
    def validate_sample(sample_id: str) -> dict:
        return tools.validate_sample(sample_id)

    return mcp, repository


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="phm-data-mcp")
    p.add_argument("--config")
    p.add_argument("--metadata")
    p.add_argument("--signals")
    p.add_argument("--backend", choices=("local", "iotdb"), default="iotdb")
    p.add_argument("--max-points", type=int, default=4096)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=6667)
    p.add_argument("--user", default="root")
    p.add_argument("--password", default="root")
    p.add_argument("--root", default="root.vibench")
    p.add_argument("--fetch-size", type=int, default=5000)
    p.add_argument("--zone-id", default="UTC")
    p.add_argument(
        "--transport", default="stdio", choices=("stdio", "sse", "streamable-http")
    )
    args = p.parse_args(argv)
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
                "default_max_points": args.max_points,
                "iotdb": {
                    "host": args.host,
                    "port": args.port,
                    "user": args.user,
                    "password": args.password,
                    "root": args.root,
                    "fetch_size": args.fetch_size,
                    "zone_id": args.zone_id,
                },
            }
        )
    mcp, repo = create_server(config)
    atexit.register(repo.close)
    mcp.run(transport=args.transport)
    return 0
