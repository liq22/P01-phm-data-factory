# Config and CI hardening

This change set hardens repository configuration parsing and makes the supported Python range continuously verifiable.

## Invariants

- Explicit `--config` takes precedence over `PHM_DATA_CONFIG`.
- Configuration roots and the nested `iotdb` section must be mapping objects.
- `PHM_DATA_BACKEND` is case-insensitive when the Python environment loader is used directly.
- Local Excel/HDF5 access requires the `legacy` optional dependency group.
- Pull requests and pushes to `main` run unit tests and wheel builds on Python 3.10 and 3.13.

## Validation

```bash
pip install -e '.[dev,agent]'
python -m compileall -q src scripts
pytest
python -m pip wheel --no-deps --no-build-isolation . -w dist
```

Live IoTDB acceptance remains opt-in through `PHM_IOTDB_LIVE=1` and is not part of the offline CI job.
