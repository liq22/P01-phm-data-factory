# phm-data-factory API Contract (v0.2)

This document is the **stable public contract** of `phm-data-factory` as a data
backend for PHM-Vibench. It is versioned independently of the package version
and changes here follow the deprecation policy below.

`phm-data-factory` provides IoTDB-backed PHM metadata, signal random-access,
sample validation, a JSON CLI, and **read-only** Agent/MCP tools. PHM-Vibench
owns split / Dataset / DataLoader / task / model / trainer — those do **not**
live in this package (see `docs/GOAL.md`).

## Stability tiers

| Tier | Meaning |
|---|---|
| **Stable** | Covered by this contract. Changes follow the deprecation policy. |
| **Internal** | Usable but not contractually stable; may change between versions. |
| **Admin** | Operational only (import/admin CLI). Do not depend on from training code. |

## Stable API (v0.2)

### `connect`

```python
from phm_data_factory import connect

with connect("config/phm-data.yaml") as repo:   # path | dict | RepositoryConfig | None(env)
    ...
```

`connect(config=None, /, **overrides) -> PHMDataRepository`. Accepts a config
file path, a mapping, an existing `RepositoryConfig`, or `None` (reads
`PHM_DATA_CONFIG` / env). Keyword `overrides` merge into the `iotdb` block.
Works for both `local` and `iotdb` backends — the return type is the same
`PHMDataRepository` either way.

### `PHMDataRepository` — the 4 operations PHM-Vibench depends on

```python
records = repo.search_samples(filters=None, limit=100, visible_only=False)  # -> list[dict]
meta    = repo.get_sample_metadata(sample_id)                               # -> dict
x       = repo.read_signal(sample_id, start=0, end=None, channels=None)     # -> np.ndarray  (NO decimation)
report  = repo.write_sample(sample_id, values, metadata=None, *, mode="error", **kw)  # -> dict
```

- `search_samples` / `get_sample_metadata`: existing methods, now part of the
  contract. `search_samples` supports task flags via the Agent aliases
  (`fault`/`anomaly`/`rul`/`digital_twin`) or direct field filters
  (`{"digital_twin_prediction": True}`).
- `read_signal`: **training path**. Returns a dense `(N, C)` ndarray with no
  decimation. For bounded previews use `get_signal_window` (Internal tier).
- `write_sample`: `mode="error"` (default) raises if the sample already exists;
  `mode="overwrite"` replaces it. Raises `TypeError` on a read-only backend
  (e.g. HDF5). `metadata` may be a `SampleMetadata`, a mapping, or `None`.

Trusted PHM-Vibench adapters may additionally call
`metadata_frame("phm_vibench_v1")`. It returns legacy column names with typed
scalar values and rejects reduced-fidelity IoTDB v1 metadata.

### Agent DataPort 1.0

`connect_agent(config, profile="benchmark_public", dataset_digest=None)` returns
context-managed, read-only `AgentDataTools`. Its manifest reports package
version `0.2.0`, API/capability schema `1.0.0`, concrete backend/dataset identity,
continuous-series/sample-index capabilities, and label visibility policy.
`benchmark_public` forces visible-only search, rejects private filters and
unlisted IDs, and removes label/target fields. MCP is locked to this profile.

## Not in the v0.2 contract (Internal / Admin / deferred)

| Symbol | Tier | Notes |
|---|---|---|
| `get_signal_window` | Internal | Bounded Agent/JSON preview (`max_points` decimation). |
| `get_signal_statistics` | Internal | Client-side numpy stats; server-side pushdown is a P1 optimization, not a contract. |
| `validate_sample`, `summary`, `list_datasets` | Internal | Used by CLI/Agent; not a training dependency. |
| `SignalStore.write` capability | n/a | Capability Protocol; reachable only via `repo.write_sample`. |
| `delete` / sample deletion | **Admin** | Not a public method in v0.2; `write_sample(..., mode="overwrite")` covers replace. |
| `read_iter` streaming | deferred (P2) | Internal `read` is already iterator-based. |
| `AgentDataTools` / MCP tools | Internal | Read-only; no write tool is exposed. |

## Capability Protocols (`phm_data_factory.stores.base`)

- `SignalStore` — read-only ABC (`read`, `shape`, `contains`, `list_ids`).
- `WritableSignalStore` — optional `write(...)` capability; the repository
  gates `write_sample` on `isinstance(store, WritableSignalStore)`.

## Versioning & deprecation policy

- Training contract is v0.2. Agent schema is reported by
  `api_schema_version="1.0.0"`; `api_version="0.2"` is a one-minor deprecated
  compatibility alias.
- **Stable** symbols: breaking changes require a contract major bump and one
  minor cycle of deprecation warnings before removal.
- **Internal** symbols: may change at any minor version.
- Adding a new Stable symbol is backward-compatible and does not bump the
  contract major version.
