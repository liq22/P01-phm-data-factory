# IoTDB Backend — Developer Guide

`phm-data-factory` exposes Apache IoTDB as a first-class **read+write** `SignalStore`
under `phm_data_factory.stores.iotdb`. This guide covers the stable v0.2 API —
see `docs/API_CONTRACT.md` for the full contract.

## One-liner connect

```python
from phm_data_factory import connect

with connect("config/phm-data.yaml") as repo:   # path | dict | RepositoryConfig | None(env)
    ...
```

`connect()` returns a `PHMDataRepository` — the same abstraction for the `local`
(HDF5) and `iotdb` backends. `backend:` in the config selects which one. With
`backend: iotdb` and **no** `metadata_path`, the sample catalog is loaded from
IoTDB's own `.meta` devices, so a fresh machine can read directly from IoTDB
without the source `metadata.xlsx`.

## The 4 stable operations

```python
with connect("config/phm-data.yaml") as repo:
    rows = repo.search_samples({"name": "RM_001_CWRU"}, limit=10)   # list[dict]
    meta = repo.get_sample_metadata("1")                            # dict
    x    = repo.read_signal("1", start=0, end=4096, channels=[0,1]) # np.ndarray (NO decimation)
    # write is IoTDB-only (HDF5 is read-only):
    report = repo.write_sample("new_id", x, metadata=meta, mode="error")  # dict
```

`read_signal` is the training path (dense ndarray). For bounded Agent/JSON
previews use `get_signal_window(max_points=...)` (not part of the contract).

`write_sample(mode=...)`: `"error"` (default) raises `FileExistsError` if the
sample already exists; `"overwrite"` clears the existing signal data first.
Deletion is **not** a stable API in v0.2 — use `mode="overwrite"` to replace.

## Direct store access

```python
from phm_data_factory.stores.iotdb import IoTDBSignalStore

store = IoTDBSignalStore.connect(host="127.0.0.1", port=6667)  # metadata=None → lazy from IoTDB
arr = store.read("1", 0, 1024, channels=[0])
store.write("2", arr, metadata={"name": "RM_001_CWRU", "sample_rate": 12000})
```

The store is `WritableSignalStore`-capable; the repository gates `write_sample`
on that capability (`isinstance(store, WritableSignalStore)`).

## How reads work (no pandas round-trip)

`read()` uses the iterator result-set → pre-allocated numpy, not `todf()`. This
matters for long signals (e.g. the 8-channel gearbox samples ~768k points).
`contains()` is O(1) when the catalog came from IoTDB (`availability_is_cheap=True`),
so `repo.summary()` can count availability cheaply.

## Importing data (unchanged)

The bulk importer still works exactly as before — it now delegates to the
store's single write path:

```bash
phm-data-iotdb check
python scripts/import_datasets.py --config config/phm-data.yaml \
    --datasets RM_016_JNU --report import-report.json
python scripts/verify_metadata.py --config config/phm-data.yaml
```

`scripts/import_datasets.py` 与 `phm-data-iotdb import` 都支持复用
`--source-manifest <json>` 或显式 `--skip-source-manifest`。默认仍完整计算
hash；跳过时 import report 不提供 dataset identity/digest。

After import, switch `backend: iotdb` and drop `metadata_path` to read purely
from IoTDB.

## PHM-Vibench integration (boundary respected)

PHM-Vibench keeps its split / Dataset / DataLoader / task / model / trainer. The
optional bridge only hands it a backend:

```python
from src.data_factory import build_data_backend
with build_data_backend(args.data) as backend:   # IoTDB if args.data.phm_data_config set, else local
    x = backend.read_signal(sample_id, start, end, channels)
```

`build_data` / task split / training are unchanged. See `docs/GOAL.md` for the
repository boundary.

## Tree path layout

```
root.vibench.<dataset>.sample_<Id>.signal.ch_<channel>   # DOUBLE/GORILLA/SNAPPY, aligned
root.vibench.<dataset>.sample_<Id>.meta.<field>          # the 16 SCHEMA fields (incl. digital_twin_prediction)
```

Timestamps are synthetic integer sample indices `0..N-1`; convert to seconds via
`sample_rate` from metadata.
