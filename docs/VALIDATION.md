# Validation record

Version: `0.2.0`

Validated locally with Python 3.13 against:

- core metadata/HDF5 API;
- IoTDB-first config defaults;
- JSON CLI;
- stable provider contract used by benchmark adapters;
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

Release-candidate result on 2026-08-01 in the `LQ_signal` Conda environment:
`76 passed, 1 skipped in 1.28s`. The skipped test is the opt-in live IoTDB
test. `compileall` and the `phm_data_factory-0.2.0` wheel build also passed.

## Historical cross-repository acceptance

Validated on 2026-07-18 against provider commit
`5580fafec2ea5615f6d3276d95e1e5a948cc0f13`. The old PHM-Vibench adapter PR
was later closed when PHMFactory v0.3 introduced a governed repository and
submodule policy. Its result remains historical implementation evidence, not
an installable overlay or a current support claim.

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

- PHM-Vibench maintained tests: `132 passed, 1 skipped, 10 warnings`;
- skipped test: CUDA-only TSPN-UXFD assembly because CUDA was unavailable;
- warnings: dependency deprecations plus unavailable NVML, with no test failure;
- PHM-Vibench config validation: `7/7` passed;
- phm-agent-benchmark: `191` tests passed and exact submodule topology passed;
- phm-data-factory: `67 passed, 1 skipped`, and the 0.2.0 wheel built.

## Live IoTDB 2.0.8 small-batch acceptance

The release candidate was revalidated on 2026-08-01 against a clean,
checksum-verified Apache IoTDB 2.0.8 standalone server. One generated 32-by-2
sample was imported in four chunks with `imported_count=1`, `failed_count=0`,
computed SHA-256 source hashes, complete provenance, and dataset digest
`sha256:349416758546379a2d2cd2eb6c324e09db7469f8eb88df7d540f0abe97763cde`.
The opt-in live test passed. The required AgentDataTools sequence also passed:
summary, structured search, metadata, two-channel statistics, a bounded 16-point
window with step 2, and validation.

On 2026-07-21 a local IoTDB 2.0.8 standalone server was validated with 12
RM_016_JNU samples. The import completed with `imported_count=12` and
`failed_count=0`; metadata comparison reported `only_in_source=0` and
`field_diffs=0`. A real sample read back bit-close to its HDF5 source at
`rtol=atol=1e-9`; statistics were finite; BOOLEAN metadata and synthetic
write/read/delete round trips passed; and the opt-in live test reported
`1 passed`.

The roughly 250 GB full import and performance thresholds were not validated.
Default source hashing remains reproducible but expensive. Operators may reuse
a precomputed source manifest or explicitly choose `--skip-source-manifest`;
the latter records incomplete provenance and no dataset digest.

Re-run the bounded acceptance on a machine with IoTDB available:

```bash
./scripts/start_iotdb.sh
phm-data-iotdb check
phm-data-iotdb import --config config/phm-data.yaml \
  --sample-id 1 --skip-source-manifest --report /tmp/iotdb-smoke.json
PHM_IOTDB_LIVE=1 pytest -q tests/test_iotdb_live.py
```
