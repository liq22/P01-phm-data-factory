# PHMFactory v0.3.1 backend integration

PHMFactory owns dataset selection, splitting, windowing, Dataset/DataLoader,
tasks and trainers. `phm-data-factory` supplies typed metadata and dense signal
arrays; it does not replace PHMFactory runtime behavior.

## Release boundary

PHMFactory v0.3.0 deliberately defers this optional backend. The governed
v0.3.1 integration must use:

```text
repository: https://github.com/PHMbench/phm-data-factory.git
path:       packages/phm-data-factory
pin:        one immutable reviewed commit, with no branch tracking
license:    Apache-2.0
```

The provider repository does not vendor or publish a consumer overlay. The
authoritative adapter and tests live in the PHMFactory pull request so they can
be reviewed against the current protected runtime.

## Adapter contract

The future configuration surface is:

```yaml
data:
  factory_name: phm_data
  phm_data_config: configs/data/cwru-iotdb.yaml
  batch_size: 32
  num_workers: 4
```

Selecting `phm_data` requires `phm_data_config` and lazily imports an installed
`phm_data_factory` package. The adapter must not mutate `sys.path`, initialize
the submodule automatically, modify the base data-factory lifecycle, or fall
back silently. Existing factory names continue to require their legacy
`data_dir` and `metadata_file` fields.

The adapter reads typed metadata with
`repo.metadata_frame("phm_vibench_v1")` and dense arrays with
`repo.read_signal()`. Older indexed IoTDB metadata must first be upgraded with:

```bash
phm-data-iotdb sync-metadata --config config/phm-data.yaml --report metadata-sync.json
```

Agent access remains separate and read-only through `connect_agent` or MCP;
IoTDB import is never exposed as an Agent tool.
