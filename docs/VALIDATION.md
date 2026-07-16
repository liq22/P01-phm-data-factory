# Validation record

Version: `0.2.0`

Validated locally with Python 3.13 against:

- core metadata/HDF5 API;
- IoTDB-first config defaults;
- JSON CLI;
- PHM-Vibench bridge loaded from its standalone module;
- FastMCP server construction with MCP 1.28;
- Apache IoTDB Python client 2.0.8 imports and method signatures;
- fake IoTDB Session writes for aligned schema, metadata records, tablet chunks.
- Agent DataPort 1.0 manifests and benchmark-public label isolation;
- path-independent dataset identity and typed IoTDB v2 metadata round-trips.

Commands:

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src
python -m pip wheel --no-deps --no-build-isolation . -w dist
```

Result: run `PYTHONPATH=src pytest -q` in the current checkout for the latest
count.

## Cross-repository v0.2 acceptance

Validated on 2026-07-16 with provider tag `v0.2.0` at
`5580fafec2ea5615f6d3276d95e1e5a948cc0f13`. Both PHM-Vibench and
phm-agent-benchmark pinned that exact commit.

PHM-Vibench was validated in the `LQ_signal` Conda environment with Python
3.10 and `pytorch_lightning 2.3.3`:

```bash
conda run -n LQ_signal env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  MPLCONFIGDIR=/tmp/phmv-matplotlib-cache \
  PYTHONPATH=packages/phm-data-factory/src:. \
  python -m pytest -p no:cacheprovider -q -rs test/

conda run -n LQ_signal env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=packages/phm-data-factory/src:. \
  python -m scripts.validate_configs
```

Results:

- PHM-Vibench maintained tests: `106 passed, 1 skipped, 6 warnings`;
- skipped test: CUDA-only TSPN-UXFD assembly because CUDA was unavailable;
- warnings: dependency deprecations plus unavailable NVML, with no test failure;
- PHM-Vibench config validation: `7/7` passed;
- phm-agent-benchmark: `191` tests passed and exact submodule topology passed;
- phm-data-factory: `67 passed, 1 skipped`, and the 0.2.0 wheel built.

The test suite does not require a running database. A live IoTDB container was
not started in the build environment; run the following acceptance check on a
machine with Docker:

```bash
./scripts/start_iotdb.sh
phm-data-iotdb check
phm-data-iotdb import --config config/phm-data.yaml \
  --sample-id 1 --report /tmp/iotdb-smoke.json
```
