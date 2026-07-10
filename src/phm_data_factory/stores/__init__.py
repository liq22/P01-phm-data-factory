from .base import SignalStore, WritableSignalStore

__all__ = [
    "SignalStore",
    "WritableSignalStore",
    "H5SignalStore",
    "DirectoryH5SignalStore",
    "H5DataDict",
    "IoTDBConfig",
    "IoTDBSignalStore",
]


def __getattr__(name: str):
    if name in {"H5SignalStore", "DirectoryH5SignalStore", "H5DataDict"}:
        try:
            from .h5 import DirectoryH5SignalStore, H5DataDict, H5SignalStore
        except ImportError as exc:
            raise RuntimeError("Install phm-data-factory[legacy] for HDF5 support") from exc
        return {
            "H5SignalStore": H5SignalStore,
            "DirectoryH5SignalStore": DirectoryH5SignalStore,
            "H5DataDict": H5DataDict,
        }[name]
    if name in {"IoTDBConfig", "IoTDBSignalStore"}:
        from .iotdb import IoTDBConfig, IoTDBSignalStore

        return {"IoTDBConfig": IoTDBConfig, "IoTDBSignalStore": IoTDBSignalStore}[name]
    raise AttributeError(name)
