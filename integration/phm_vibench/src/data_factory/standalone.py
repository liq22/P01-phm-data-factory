"""Optional bridge from PHM-Vibench configs to ``phm-data-factory``.

This module does not participate in the benchmark training pipeline. It only
constructs the standalone repository and read-only Agent tool surface from the
existing ``data`` config block.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _load_api():
    try:
        from phm_data_factory import AgentDataTools, PHMDataRepository
    except ModuleNotFoundError:
        # Source-checkout fallback. Normal installations should use
        # ``pip install -e packages/phm-data-factory`` instead.
        repo_root = Path(__file__).resolve().parents[2]
        package_src = repo_root / "packages" / "phm-data-factory" / "src"
        if not package_src.exists():
            raise ModuleNotFoundError(
                "phm-data-factory is not installed and the monorepo package "
                f"was not found at {package_src}"
            )
        sys.path.insert(0, str(package_src))
        from phm_data_factory import AgentDataTools, PHMDataRepository
    return AgentDataTools, PHMDataRepository


def _value(config: Any, name: str, default: Any = None) -> Any:
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _resolve_under_data_dir(data_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (data_dir / path).resolve()


def build_data_repository(args_data: Any, signal_path: str | Path | None = None):
    """Create the standalone repository from PHM-Vibench's data config.

    The caller owns the returned repository and must call ``close()`` or use it
    as a context manager.
    """
    _, repository_cls = _load_api()
    data_dir = Path(_value(args_data, "data_dir", "data")).expanduser().resolve()
    metadata_file = _value(args_data, "metadata_file", "metadata.xlsx")
    metadata_path = _resolve_under_data_dir(data_dir, metadata_file)

    configured_signal = signal_path or _value(args_data, "agent_signal_path")
    if configured_signal:
        signals = _resolve_under_data_dir(data_dir, configured_signal)
    else:
        cache = data_dir / "cache.h5"
        signals = cache if cache.exists() else data_dir
    return repository_cls.from_local(metadata_path, signals)


def build_agent_data_tools(
    args_data: Any,
    signal_path: str | Path | None = None,
    default_max_points: int | None = None,
):
    """Create bounded, read-only Agent tools from the existing data config."""
    tools_cls, _ = _load_api()
    repository = build_data_repository(args_data, signal_path=signal_path)
    max_points = default_max_points
    if max_points is None:
        max_points = int(_value(args_data, "agent_max_points", 4096))
    return tools_cls(repository, default_max_points=max_points)
