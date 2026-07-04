# Goal: standalone Agent-ready PHM data layer

## Outcome

Extract PHM metadata and signal access behind a stable package that local
agents can consume through Apache IoTDB, while keeping task splits, PyTorch
datasets, samplers, models, and trainers inside PHM-Vibench.

## Deliverables

1. Installable `phm-data-factory` wheel and source distribution.
2. IoTDB repository API keyed by Vibench `Id`.
3. Optional legacy metadata + HDF5 import path for migration.
4. Bounded read-only Agent tools and MCP server.
5. Thin PHM-Vibench adapter with no change to `build_data()`.
6. Unit tests and a live-IoTDB smoke-test command.

## Acceptance criteria

- IoTDB metadata is indexed without changing public sample fields.
- Legacy CSV/XLSX metadata and HDF5 caches can be imported into IoTDB.
- Runtime CLI/MCP/Agent queries do not require local metadata or HDF5 files.
- Agent waveform responses are bounded and report their downsampling step.
- IoTDB import writes aligned channels and mirrors sample metadata.
- Package imports without PyTorch or PHM-Vibench.
- PHM-Vibench continues using its current factory and DataLoader contracts.
