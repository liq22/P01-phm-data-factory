"""IoTDB tree-path encoding for samples and metadata devices."""

from __future__ import annotations
import hashlib
import re
import unicodedata
from typing import Any


_SAMPLE_RE = re.compile(r"\.sample_([^\.]+)\.(?:signal|meta)$")


class IoTDBPathCodec:
    @staticmethod
    def segment(value: Any, allow_digit=False):
        raw = str(value).strip()
        norm = unicodedata.normalize("NFKC", raw)
        safe = re.sub(r"[^A-Za-z0-9_]", "_", norm)
        safe = re.sub(r"_+", "_", safe).strip("_") or "item"
        if safe[0].isdigit() and not allow_digit:
            safe = "x_" + safe
        if safe != norm:
            safe += "_" + hashlib.sha1(raw.encode()).hexdigest()[:8]
        return safe

    @classmethod
    def signal_device(cls, config, record):
        dataset = cls.segment(
            record.name or f"dataset_{record.dataset_id or 'unknown'}"
        )
        return f"{config.root}.{dataset}.sample_{cls.segment(record.sample_id, True)}.signal"

    @classmethod
    def metadata_device(cls, config, record):
        return cls.signal_device(config, record).rsplit(".", 1)[0] + ".meta"

    # --- inverse helpers (used by the DB-backed sample index) ---
    @staticmethod
    def sample_id_from_device(device: str) -> str | None:
        """Extract the encoded sample_id segment from a signal/meta device path."""
        match = _SAMPLE_RE.search(str(device))
        return match.group(1) if match else None

    @staticmethod
    def dataset_from_device(device: str) -> str | None:
        """Best-effort encoded dataset segment (the segment before ``sample_``)."""
        match = re.match(rf"^.+\.([^.]+)\.sample_[^.]+\.(?:signal|meta)$", str(device))
        return match.group(1) if match else None
