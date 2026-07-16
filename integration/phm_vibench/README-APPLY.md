# Apply to PHM-Vibench

This overlay is prepared against PHM-Vibench commit
`d9b0d7fea121cb028b9275704f412fefc49560d2` and supplies the registered
`phm_data` factory plus bridge tests/docs. The accompanying consumer patch also
updates conditional config validation and experiment naming.

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
