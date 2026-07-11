"""Standalone PHM data layer."""

from .agent import AgentDataTools
from .config import RepositoryConfig, build_repository, connect
from .metadata import MetadataAccessor, MetadataCatalog, read_metadata, smart_read_csv
from .models import SampleMetadata, SignalWindow
from .repository import PHMDataRepository
from .stores import SignalStore, WritableSignalStore

__version__ = "0.1.0"
__all__ = [
    "AgentDataTools",
    "RepositoryConfig",
    "build_repository",
    "connect",
    "MetadataAccessor",
    "MetadataCatalog",
    "read_metadata",
    "smart_read_csv",
    "SampleMetadata",
    "SignalWindow",
    "PHMDataRepository",
    "DirectoryH5SignalStore",
    "H5DataDict",
    "H5SignalStore",
    "SignalStore",
    "WritableSignalStore",
]


def __getattr__(name: str):
    if name in {"DirectoryH5SignalStore", "H5DataDict", "H5SignalStore"}:
        from .stores import DirectoryH5SignalStore, H5DataDict, H5SignalStore

        return {
            "DirectoryH5SignalStore": DirectoryH5SignalStore,
            "H5DataDict": H5DataDict,
            "H5SignalStore": H5SignalStore,
        }[name]
    raise AttributeError(name)
