"""Apache IoTDB backend for phm-data-factory (Store layer).

The back-compat module ``phm_data_factory.iotdb`` re-exports everything below;
new code may import directly from ``phm_data_factory.stores.iotdb``.
"""

from .config import IoTDBConfig
from .session import IoTDBSession
from .paths import IoTDBPathCodec
from .metadata import load_metadata_from_iotdb
from .schema import SCHEMA
from .store import IoTDBSignalStore
from .bulk import (
    IoTDBImporter,
    build_iotdb_data_manifest,
    build_source_manifest,
)

__all__ = [
    "IoTDBConfig",
    "IoTDBSession",
    "IoTDBPathCodec",
    "load_metadata_from_iotdb",
    "SCHEMA",
    "IoTDBSignalStore",
    "IoTDBImporter",
    "build_source_manifest",
    "build_iotdb_data_manifest",
]
