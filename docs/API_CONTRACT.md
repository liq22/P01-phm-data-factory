# Public backend contract

`phm-data-factory` is the data-backend boundary used by PHM-Vibench. Task
splits, window policies, PyTorch Dataset/DataLoader objects, models, and
trainers remain in PHM-Vibench.

## Stability

The stable Python contract is versioned independently from the package:

```python
AgentDataTools.manifest()["api_version"] == "0.2"
```

Additive changes are allowed within `0.2`. Removing a method, changing an
argument's meaning, or changing an output shape requires a new API version and
a deprecation period.

## Minimal repository surface

```python
from phm_data_factory import connect

with connect("config/phm-data.yaml") as repo:
    rows = repo.search_samples({"domain_id": 0}, limit=None)
    metadata = repo.get_sample_metadata("1")
    values = repo.read_signal("1", start=0, end=4096, channels=[0, 1])
```

The stable read surface is:

- `search_samples(filters=None, limit=100, visible_only=False)`
- `get_sample_metadata(sample_id)`
- `read_signal(sample_id, start=0, end=None, channels=None)`

`read_signal` always returns a full-resolution NumPy array with canonical shape
`(length, selected_channels)`. Agent and MCP callers should continue using
`get_signal_window`, whose bounded response is JSON-safe.

A mutable backend additionally supports:

```python
repo.write_sample(
    "generated-1",
    values,
    metadata={
        "name": "synthetic-bearing",
        "sample_rate": 12000,
        "digital_twin_prediction": True,
    },
)
```

`write_sample` raises `TypeError` for read-only stores. The default IoTDB write
mode is `error`; migration code uses explicit `mode="upsert"` for backward
compatible, idempotent imports.

## Read-only Agent boundary

The Python repository can be writable while `AgentDataTools`, MCP, and the JSON
query CLI remain read-only. No write or delete tool is exposed to an LLM-facing
surface.

## Backend rules

1. `sample_id` is the global primary key.
2. Signal timestamps are sample indices. The first sample is timestamp `0`
   unless `base_time` is explicitly supplied.
3. Signal arrays are normalized to two dimensions and stored as `float64`.
4. IoTDB publishes `.meta` after all signal chunks. A metadata row therefore
   marks a committed sample; interrupted writes are not visible to readers.
5. PHM-Vibench owns task semantics, split generation, and window construction.
   The backend only stores metadata and signal arrays.
