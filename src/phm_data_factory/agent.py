"""Bounded JSON-safe tools for local agents."""

from __future__ import annotations
from typing import Any, Mapping, Sequence

from .contract import agent_contract_manifest
from .repository import PHMDataRepository

_PUBLIC_SAMPLE_FIELDS = {
    "sample_id",
    "dataset_id",
    "name",
    "domain_id",
    "sample_rate",
    "sample_length",
    "channels",
    "visible",
    "backend",
    "time_basis",
    "unit",
    "modality",
    "signal_available",
    "stored_shape",
    "metadata_digest",
}

def _public_record(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in _PUBLIC_SAMPLE_FIELDS if key in value}


class AgentDataTools:
    def __init__(
        self,
        repository: PHMDataRepository,
        default_max_points: int = 4096,
        *,
        profile: str = "research",
        backend_kind: str = "runtime_selected",
        dataset_digest: str | None = None,
    ):
        if profile not in {"research", "benchmark_public"}:
            raise ValueError("profile must be 'research' or 'benchmark_public'")
        self.repository = repository
        self.default_max_points = int(default_max_points)
        self.profile = profile
        self.backend_kind = str(backend_kind)
        self.dataset_digest = dataset_digest

    @property
    def _public(self) -> bool:
        return self.profile == "benchmark_public"

    def _require_public_sample(self, sample_id: str) -> dict[str, Any]:
        record = self.repository.get_sample_metadata(sample_id)
        if record.get("visible") is not True:
            raise KeyError(sample_id)
        return record

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
        if self._public and (label is not None or extra_filters):
            raise ValueError("benchmark_public only supports structured public filters")
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
                "digital_twin": "digital_twin_prediction",
                "digital_twin_prediction": "digital_twin_prediction",
            }
            if task.lower() not in aliases:
                raise ValueError(f"Unknown task: {task}")
            filters[aliases[task.lower()]] = True
        records = self.repository.search_samples(
            filters, limit, True if self._public else visible_only
        )
        return [_public_record(item) for item in records] if self._public else records

    def get_sample_metadata(self, sample_id: str):
        result = (
            self._require_public_sample(sample_id)
            if self._public
            else self.repository.get_sample_metadata(sample_id)
        )
        return _public_record(result) if self._public else result

    def get_signal_window(
        self,
        sample_id: str,
        start: int = 0,
        end: int | None = None,
        channels: Sequence[int] | None = None,
        max_points: int | None = None,
    ):
        if self._public:
            self._require_public_sample(sample_id)
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
        if self._public:
            self._require_public_sample(sample_id)
        return self.repository.get_signal_statistics(
            sample_id, start, end, channels, max_points
        )

    def validate_sample(self, sample_id: str):
        if self._public:
            self._require_public_sample(sample_id)
        return self.repository.validate_sample(sample_id)

    def close(self) -> None:
        self.repository.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def manifest(self=None):
        """Return a generic class contract or a concrete instance manifest."""

        if not isinstance(self, AgentDataTools):
            return agent_contract_manifest()
        policy = (
            "public_evaluator_private_v1"
            if self._public
            else "legacy_metadata_surface_to_be_versioned"
        )
        return agent_contract_manifest(
            backend_kind=self.backend_kind,
            dataset_digest=self.dataset_digest,
            label_visibility_policy=policy,
        )
