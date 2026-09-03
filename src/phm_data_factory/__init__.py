"""Standalone PHM data layer."""

from .agent import AgentDataTools
from .config import RepositoryConfig, build_repository, connect, connect_agent
from .contract import PACKAGE_VERSION, agent_contract_manifest
from .data_port import AgentDataPort, StreamCursor
from .identity import build_dataset_identity, load_dataset_identity
from .metadata import MetadataAccessor, MetadataCatalog, read_metadata, smart_read_csv
from .models import SampleMetadata, SignalWindow
from .repository import PHMDataRepository
from .stores import DirectoryCSVSignalStore, SignalStore, WritableSignalStore

__version__ = PACKAGE_VERSION
__all__ = [
    "AgentDataTools",
    "AgentDataPort",
    "StreamCursor",
    "RepositoryConfig",
    "build_repository",
    "connect",
    "connect_agent",
    "agent_contract_manifest",
    "build_dataset_identity",
    "load_dataset_identity",
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
    "DirectoryCSVSignalStore",
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
