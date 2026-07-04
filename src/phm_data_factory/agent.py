"""Bounded JSON-safe tools for local agents."""

from __future__ import annotations
from typing import Any, Mapping, Sequence
from .repository import PHMDataRepository


class AgentDataTools:
    def __init__(self, repository: PHMDataRepository, default_max_points: int = 4096):
        self.repository = repository
        self.default_max_points = int(default_max_points)

    def repository_summary(self):
        return self.repository.summary()

    def list_datasets(self):
        return self.repository.list_datasets()

    def search_samples(
        self,
        dataset_id: Any = None,
        name: str | None = None,
        label: Any = None,
        domain_id: Any = None,
        task: str | None = None,
        visible_only: bool = False,
        limit: int = 50,
        extra_filters: Mapping[str, Any] | None = None,
    ):
        filters = dict(extra_filters or {})
        for key, value in {
            "dataset_id": dataset_id,
            "name": name,
            "label": label,
            "domain_id": domain_id,
        }.items():
            if value is not None:
                filters[key] = value
        if task:
            aliases = {
                "fault": "fault_diagnosis",
                "fault_diagnosis": "fault_diagnosis",
                "anomaly": "anomaly_detection",
                "anomaly_detection": "anomaly_detection",
                "rul": "remaining_life",
                "remaining_life": "remaining_life",
            }
            if task.lower() not in aliases:
                raise ValueError(f"Unknown task: {task}")
            filters[aliases[task.lower()]] = True
        return self.repository.search_samples(filters, limit, visible_only)

    def get_sample_metadata(self, sample_id: str):
        return self.repository.get_sample_metadata(sample_id)

    def get_signal_window(
        self,
        sample_id: str,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        max_points: int | None = None,
    ):
        return self.repository.get_signal_window(
            sample_id,
            start,
            end,
            channels,
            self.default_max_points if max_points is None else max_points,
        ).to_dict()

    def get_signal_statistics(
        self,
        sample_id: str,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        max_points: int = 100000,
    ):
        return self.repository.get_signal_statistics(
            sample_id, start, end, channels, max_points
        )

    def validate_sample(self, sample_id: str):
        return self.repository.validate_sample(sample_id)

    def close(self) -> None:
        self.repository.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @staticmethod
    def manifest():
        return {
            "name": "phm-data-factory",
            "version": "0.1.0",
            "read_only": True,
            "tools": [
                "repository_summary",
                "list_datasets",
                "search_samples",
                "get_sample_metadata",
                "get_signal_window",
                "get_signal_statistics",
                "validate_sample",
            ],
        }
