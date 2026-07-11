"""IoTDB session management.

``_imports`` is owned by the back-compat shim (``phm_data_factory.iotdb``) so
that tests monkeypatching ``phm_data_factory.iotdb._imports`` propagate here.
It is resolved with a function-local import at call time — this both picks up
the monkeypatch (attribute lookup on the shim module each call) and avoids any
module-load import cycle.
"""

from __future__ import annotations
from .config import IoTDBConfig


class IoTDBSession:
    def __init__(self, config: IoTDBConfig):
        self.config, self.session = config, None

    def open(self):
        if self.session is None:
            from ...iotdb import _imports

            Session, *_ = _imports()
            self.session = Session(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                fetch_size=self.config.fetch_size,
                zone_id=self.config.zone_id,
            )
            self.session.open(enable_rpc_compression=False)
        return self.session

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
