# phm-data-factory

中文快速开始：[`docs/QUICKSTART_ZH.md`](docs/QUICKSTART_ZH.md)

Standalone, read-only-first PHM data layer extracted from PHM-Vibench. The
runtime path is Apache IoTDB: CLI, Python, and MCP tools query one IoTDB tree
without requiring local `metadata.xlsx` files or HDF5 caches in the agent
process.

## Boundary

`phm-data-factory` owns IoTDB-backed metadata lookup, signal random access,
validation, JSON CLI, and read-only Agent tools. PHM-Vibench keeps dataset
splitting, PyTorch Datasets/DataLoaders, task policy, models, and trainers.

Legacy `metadata.xlsx/CSV + HDF5` support is retained only for migration into
IoTDB.

## Install

```bash
pip install -e .
pip install -e '.[yaml,agent]'
```

Install legacy import support only when migrating old local files:

```bash
pip install -e '.[legacy]'
```

## IoTDB Runtime

```bash
cd docker/iotdb
docker compose up -d
phm-data-iotdb check
```

Query IoTDB directly:

```bash
phm-data --root root.vibench summary
phm-data --root root.vibench window 1 \
  --start 0 --end 12000 --channels 0,1 --max-points 1024
```

All output is JSON. Agent-facing windows are bounded and report `step`; when
`step > 1`, the values are a preview rather than a model-training tensor.

Python:

```python
from phm_data_factory import AgentDataTools, RepositoryConfig, build_repository

config = RepositoryConfig.from_mapping(
    {"backend": "iotdb", "iotdb": {"root": "root.vibench"}}
)

with build_repository(config) as repo:
    tools = AgentDataTools(repo)
    print(tools.search_samples(task="fault_diagnosis", limit=10))
```

## MCP

```bash
phm-data-mcp --config /absolute/path/phm-data.iotdb.yaml
```

Client configuration:

```json
{
  "mcpServers": {
    "phm-data": {
      "command": "/absolute/path/to/venv/bin/phm-data-mcp",
      "args": ["--config", "/absolute/path/phm-data.iotdb.yaml"]
    }
  }
}
```

Read-only tools: `repository_summary`, `list_datasets`, `search_samples`,
`get_sample_metadata`, `get_signal_window`, `get_signal_statistics`, and
`validate_sample`.

## Legacy Import

Old Vibench files can be imported once, then runtime queries no longer need the
local metadata/HDF5 pair:

```bash
phm-data-iotdb import \
  --metadata /absolute/path/metadata.xlsx \
  --signals /absolute/path/data \
  --root root.vibench \
  --report import-report.json
```

The IoTDB layout is:

```text
root.vibench.<dataset>.sample_<Id>.signal.ch_<channel>
root.vibench.<dataset>.sample_<Id>.meta.<field>
```

Timestamps are sample indices `0..L-1`; channels are aligned. Metadata is
mirrored at timestamp `0`, allowing an IoTDB-only Agent configuration.

## PHM-Vibench Bridge

The `integration/phm_vibench/` directory contains the thin adapter and the
exact files intended for the PHM-Vibench repository. It adds only
`build_data_repository` and `build_agent_data_tools`; the existing
`build_data()` training entrypoint is unchanged.

## Test and Build

```bash
pytest
python -m pip wheel --no-deps --no-build-isolation .
```
