"""Standalone PHM data layer."""

from .agent import AgentDataTools
from .config import RepositoryConfig, build_repository
from .contract import API_SCHEMA_VERSION, PACKAGE_VERSION, agent_contract_manifest
from .metadata import MetadataAccessor, MetadataCatalog, read_metadata, smart_read_csv
from .models import SampleMetadata, SignalWindow
from .repository import PHMDataRepository
from .stores import SignalStore

__version__ = PACKAGE_VERSION
__all__ = [
    "AgentDataTools",
    "API_SCHEMA_VERSION",
    "PACKAGE_VERSION",
    "agent_contract_manifest",
    "RepositoryConfig",
    "build_repository",
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
