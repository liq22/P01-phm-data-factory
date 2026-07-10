# Standalone PHM data access

PHM-Vibench keeps the existing training contract. The optional
`packages/phm-data-factory` package exposes a local or IoTDB-backed runtime data
layer to scripts and local agents without importing PyTorch, task datasets,
samplers, or trainers. Legacy metadata/HDF5 inputs remain available for
migration and bridge compatibility.

## Install

```bash
pip install -e 'packages/phm-data-factory[yaml,agent,legacy]'
```

## Backend selection from the existing data block

The bridge does not modify `build_data()`. It only adds
`build_data_repository()` and `build_agent_data_tools()`.

For the original local behavior, no new field is required:

```python
from src.data_factory import build_agent_data_tools

with build_agent_data_tools(args.data) as tools:
    print(tools.repository_summary())
    print(tools.get_sample_metadata("1"))
```

The legacy bridge resolves `data.data_dir`, `data.metadata_file`, and
`cache.h5`. If the consolidated cache does not yet exist, it reads `<Name>.h5`
files from the data directory.

To select the shared backend explicitly, add one field to the existing `data`
block:

```yaml
data:
  data_dir: /path/to/PHM-Vibench
  phm_data_config: phm-data.yaml
```

A relative `phm_data_config` path is resolved under `data_dir`; an absolute path
is used as-is. The referenced file can select either backend:

```yaml
backend: iotdb

default_max_points: 4096

iotdb:
  host: 127.0.0.1
  port: 6667
  user: root
  password: root
  root: root.vibench
```

Then the same bridge call returns an IoTDB-backed repository:

```python
from src.data_factory import build_data_repository

with build_data_repository(args.data) as repo:
    records = repo.search_samples({"domain_id": 0}, limit=None)
    values = repo.read_signal(records[0]["sample_id"], 0, 4096, channels=[0, 1])
```

Task splits, window policies, Dataset/DataLoader objects, labels, models, and
trainers remain in PHM-Vibench. Only metadata lookup and signal I/O cross the
backend boundary.

## Run a local MCP server

Create an IoTDB config such as `examples/phm-data.iotdb.yaml`, then:

```bash
phm-data-mcp --config /absolute/path/phm-data.iotdb.yaml
```

The Agent surface is read-only and returns bounded waveform previews. Training
code should use the Python repository directly with `read_signal()` when it
needs complete arrays.
