# PHM-Vibench training backend

PHM-Vibench owns dataset selection, splitting, windowing, Dataset/DataLoader,
tasks and trainers. `phm-data-factory` supplies typed metadata and dense signal
arrays through the unchanged `build_data(args_data, args_task)` entry point.

## Install the exact provider revision

Both PHM-Vibench and phm-agent-benchmark must pin the same `v0.2.0` commit as a
Git submodule. From PHM-Vibench:

```bash
git submodule update --init packages/phm-data-factory
pip install -e 'packages/phm-data-factory[yaml,legacy]'
```

## Configure training

```yaml
data:
  factory_name: phm_data
  phm_data_config: configs/data/cwru-iotdb.yaml
  dataset_name: CWRU  # optional; used in output naming
  batch_size: 32
  num_workers: 4
```

`phm_data_config` is required and may select either `local` or `iotdb`.
There is no silent fallback to `data_dir`/`metadata_file`. Other factory names
retain the legacy requirements.

The registered factory obtains metadata with
`repo.metadata_frame("phm_vibench_v1")` and signals with `repo.read_signal()`.
IoTDB metadata must be typed v2; if an older import is detected, run:

```bash
phm-data-iotdb sync-metadata --config config/phm-data.yaml --report metadata-sync.json
```

## Optional Agent access

```python
from src.data_factory import build_agent_data_tools

with build_agent_data_tools(args.data) as tools:
    print(tools.search_samples(task="fault_diagnosis", limit=10))
```

This helper defaults to `benchmark_public`: visible samples only, no label or
target fields, bounded windows, and no write/import operation.
