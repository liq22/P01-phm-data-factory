"""Lazy Apache IoTDB Session lifecycle."""

from __future__ import annotations


class IoTDBSession:
    def __init__(self, config):
        self.config, self.session = config, None

    def open(self):
        if self.session is None:
            # Resolve through the compatibility module so existing monkeypatches
            # on phm_data_factory.iotdb._imports keep working.
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
            self.session.open(
                enable_rpc_compression=self.config.enable_rpc_compression
            )
        return self.session

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
