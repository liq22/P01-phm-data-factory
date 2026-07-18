# Apply to PHM-Vibench

This overlay is prepared against PHM-Vibench commit
`a331769d4005018bc833534ecf4efeb5e8a5a78d` and supplies the registered
`phm_data` factory plus bridge tests/docs. The accompanying consumer patch also
updates conditional config validation, experiment naming, documentation scope,
and validation of initialized Git submodules.

The final consumer commit must add `packages/phm-data-factory` as a submodule
at the exact `v0.2.0` commit used by phm-agent-benchmark. Then run:

```bash
git submodule update --init packages/phm-data-factory
pip install -e 'packages/phm-data-factory[yaml,legacy]'
python -m scripts.validate_configs
PYTHONPATH=. python -m pytest -q test/test_phm_data_factory_backend.py
```

Training configuration:

```yaml
data:
  factory_name: phm_data
  phm_data_config: configs/data/cwru-iotdb.yaml
  dataset_name: CWRU
```

`build_data(args_data, args_task)` is unchanged. Missing `phm_data_config` is an
error; the adapter never silently switches to a local HDF5 backend.
