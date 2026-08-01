"""IoTDB backend quickstart — the v0.2 stable contract in one file.

Run after starting IoTDB and importing at least one dataset:
    python examples/iotdb_backend_quickstart.py

Uses connect() + the 4 stable ops (search_samples / get_sample_metadata /
read_signal / write_sample). Demonstrates that local and iotdb backends share
the same PHMDataRepository abstraction.
"""
from __future__ import annotations

import numpy as np

from phm_data_factory import WritableSignalStore, connect


def main() -> None:
    # connect() accepts a config path, dict, RepositoryConfig, or None (env).
    # With backend: iotdb and no metadata_path, the catalog is read from IoTDB.
    repo = connect("config/phm-data.yaml")
    with repo:
        print("summary:", repo.summary())

        sid = repo.metadata.keys()[0]
        print("metadata:", repo.get_sample_metadata(sid))

        x = repo.read_signal(sid, start=0, end=1024, channels=[0, 1])
        print("read_signal shape:", x.shape, "dtype:", x.dtype)

        rows = repo.search_samples({"name": repo.metadata.get(sid).name}, limit=5)
        print("search_samples:", len(rows), "rows")

        # write_sample is IoTDB-only; on the local/HDF5 backend it raises TypeError.
        if isinstance(repo.signals, WritableSignalStore):
            synthetic = np.zeros((8, 2), dtype=np.float64)
            try:
                report = repo.write_sample(
                    "demo_" + sid, synthetic,
                    metadata=repo.get_sample_metadata(sid), mode="error",
                )
                print("write_sample:", report)
            except FileExistsError:
                print("write_sample: sample already exists (use mode='overwrite')")


if __name__ == "__main__":
    main()
