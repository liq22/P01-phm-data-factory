# Standalone PHM data access

PHM-Vibench keeps the existing training contract. The optional
`packages/phm-data-factory` package exposes an IoTDB-backed runtime data layer
to scripts and local agents without importing PyTorch, task datasets, samplers,
or trainers. Legacy metadata/HDF5 inputs remain available for migration and
bridge compatibility.

## Install

```bash
pip install -e 'packages/phm-data-factory[yaml,agent,legacy]'
```

## Use the existing data config

```python
from src.data_factory import build_agent_data_tools

with build_agent_data_tools(args.data) as tools:
    print(tools.repository_summary())
    print(tools.get_sample_metadata("1"))
```

The legacy bridge resolves `data.data_dir`, `data.metadata_file`, and
`cache.h5`. If the consolidated cache does not yet exist, it reads `<Name>.h5`
files from the data directory.

## Run a local MCP server

Create an IoTDB config such as `examples/phm-data.iotdb.yaml`, then:

```bash
phm-data-mcp --config /absolute/path/phm-data.iotdb.yaml
```

The Agent surface is read-only and returns bounded waveform previews. Training
code should use the Python repository directly with `max_points=None` when it
needs complete tensors.
