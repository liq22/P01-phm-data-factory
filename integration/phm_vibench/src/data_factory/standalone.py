"""Optional bridge from PHM-Vibench configs to ``phm-data-factory``.

This module does not participate in the benchmark training pipeline. It only
constructs the standalone repository / read-only Agent tool surface / data
backend from the existing ``data`` config block. Split / window / label /
domain logic stays in PHM-Vibench.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _load_module():
    try:
        import phm_data_factory
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
        import phm_data_factory
    return phm_data_factory


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
    module = _load_module()
    data_dir = Path(_value(args_data, "data_dir", "data")).expanduser().resolve()
    metadata_file = _value(args_data, "metadata_file", "metadata.xlsx")
    metadata_path = _resolve_under_data_dir(data_dir, metadata_file)

    configured_signal = signal_path or _value(args_data, "agent_signal_path")
    if configured_signal:
        signals = _resolve_under_data_dir(data_dir, configured_signal)
    else:
        cache = data_dir / "cache.h5"
        signals = cache if cache.exists() else data_dir
    return module.PHMDataRepository.from_local(metadata_path, signals)


def build_agent_data_tools(
    args_data: Any,
    signal_path: str | Path | None = None,
    default_max_points: int | None = None,
):
    """Create bounded, read-only Agent tools from the existing data config."""
    module = _load_module()
    repository = build_data_repository(args_data, signal_path=signal_path)
    max_points = default_max_points
    if max_points is None:
        max_points = int(_value(args_data, "agent_max_points", 4096))
    return module.AgentDataTools(repository, default_max_points=max_points)


def build_data_backend(
    args_data: Any, signal_path: str | Path | None = None
):
    """Return a ``PHMDataRepository`` as the stable v0.2 read+write data backend.

    Prefers an IoTDB backend when ``phm_data_config`` is set in the data config
    (a path to a phm-data-factory yaml); otherwise builds a local HDF5
    repository. Consumed via the contract: ``search_samples``,
    ``get_sample_metadata``, ``read_signal``, ``write_sample``. The caller owns
    the repository.
    """
    module = _load_module()
    phm_cfg = _value(args_data, "phm_data_config")
    if phm_cfg:
        data_dir = Path(_value(args_data, "data_dir", ".")).expanduser().resolve()
        cfg_path = _resolve_under_data_dir(data_dir, phm_cfg)
        return module.connect(str(cfg_path))
    return build_data_repository(args_data, signal_path=signal_path)
