"""Stable mapping between PHM sample identifiers and IoTDB tree paths."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


class IoTDBPathCodec:
    @staticmethod
    def segment(value: Any, allow_digit: bool = False) -> str:
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
    def signal_device(cls, config, record) -> str:
        dataset = cls.segment(
            record.name or f"dataset_{record.dataset_id or 'unknown'}"
        )
        sample = cls.segment(record.sample_id, True)
        return f"{config.root}.{dataset}.sample_{sample}.signal"

    @classmethod
    def metadata_device(cls, config, record) -> str:
        return cls.signal_device(config, record).rsplit(".", 1)[0] + ".meta"

    @staticmethod
    def sample_id_from_device(device: str) -> str | None:
        match = re.search(r"\.sample_([^\.]+)\.(?:signal|meta)$", str(device))
        return match.group(1) if match else None

    @staticmethod
    def dataset_from_device(device: str, root: str | None = None) -> str | None:
        text = str(device)
        prefix = f"{str(root).rstrip('.')}." if root else ""
        if prefix and text.startswith(prefix):
            text = text[len(prefix) :]
        match = re.match(r"([^\.]+)\.sample_[^\.]+\.(?:signal|meta)$", text)
        return match.group(1) if match else None

    @staticmethod
    def signal_from_metadata_device(device: str) -> str:
        text = str(device)
        if not text.endswith(".meta"):
            raise ValueError(f"Expected metadata device, got {device}")
        return text.rsplit(".", 1)[0] + ".signal"
