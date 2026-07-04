# Validation record

Version: `0.1.0`

Validated locally with Python 3.13 against:

- core metadata/HDF5 API;
- IoTDB-first config defaults;
- JSON CLI;
- PHM-Vibench bridge loaded from its standalone module;
- FastMCP server construction with MCP 1.28;
- Apache IoTDB Python client 2.0.8 imports and method signatures;
- fake IoTDB Session writes for aligned schema, metadata records, tablet chunks.

Commands:

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src
python -m pip wheel --no-deps --no-build-isolation . -w dist
```

Result: run `PYTHONPATH=src pytest -q` in the current checkout for the latest
count.

The test suite does not require a running database. A live IoTDB container was
not started in the build environment; run the following acceptance check on a
machine with Docker:

```bash
./scripts/start_iotdb.sh
phm-data-iotdb check
phm-data-iotdb import \
  --metadata /absolute/path/metadata.xlsx \
  --signals /absolute/path/data \
  --sample-id 1 \
  --report /tmp/iotdb-smoke.json
```
