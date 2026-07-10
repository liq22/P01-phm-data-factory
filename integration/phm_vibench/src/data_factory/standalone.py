"""Optional bridge from PHM-Vibench configs to ``phm-data-factory``.

This module does not participate in the benchmark training pipeline. It only
constructs the standalone repository and read-only Agent tool surface from the
existing ``data`` config block.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping


def _load_api():
    try:
        from phm_data_factory import AgentDataTools, PHMDataRepository, connect
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
        from phm_data_factory import AgentDataTools, PHMDataRepository, connect
    return AgentDataTools, PHMDataRepository, connect


def _value(config: Any, name: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(name, default)
    return getattr(config, name, default)


def _resolve_under_data_dir(data_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (data_dir / path).resolve()


def _backend_config(args_data: Any, data_dir: Path):
    """Return an explicit factory config, resolving path values under data_dir."""
    configured = _value(args_data, "phm_data_config")
    if configured is None:
        configured = _value(args_data, "agent_data_config")
    if configured is None:
        return None
    if isinstance(configured, (str, Path)):
        if not str(configured).strip():
            return None
        return _resolve_under_data_dir(data_dir, configured)
    return configured


def build_data_repository(args_data: Any, signal_path: str | Path | None = None):
    """Create a standalone repository without changing PHM-Vibench ``build_data``.

    When ``data.phm_data_config`` (or the compatibility alias
    ``data.agent_data_config``) is present, it is passed to the package-level
    ``connect`` entry and may select either the local or IoTDB backend. Without
    that field, the existing metadata/HDF5 resolution is preserved verbatim.

    The caller owns the returned repository and must call ``close()`` or use it
    as a context manager.
    """
    _, repository_cls, connect_api = _load_api()
    data_dir = Path(_value(args_data, "data_dir", "data")).expanduser().resolve()
    configured_backend = _backend_config(args_data, data_dir)
    if configured_backend is not None:
        return connect_api(configured_backend)

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
    tools_cls, _, _ = _load_api()
    repository = build_data_repository(args_data, signal_path=signal_path)
    max_points = default_max_points
    if max_points is None:
        max_points = int(_value(args_data, "agent_max_points", 4096))
    return tools_cls(repository, default_max_points=max_points)
