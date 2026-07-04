"""Metadata loading and structured search."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd

from .models import SampleMetadata, clean_value, id_text

ALIASES = {
    "sample_id": ("Id", "id", "sample_id"),
    "dataset_id": ("Dataset_id", "dataset_id"),
    "name": ("Name", "name"),
    "visible": ("Visiable", "Visible", "visible"),
    "label": ("Label", "label"),
    "domain_id": ("Domain_id", "domain_id"),
    "sample_rate": ("Sample_rate", "sample_rate"),
    "sample_length": ("Sample_lenth", "Sample_length", "sample_length"),
    "channels": ("Channel", "Channels", "channels"),
    "fault_diagnosis": ("Fault_Diagnosis", "fault_diagnosis"),
    "anomaly_detection": ("Anomaly_Detection", "anomaly_detection"),
    "remaining_life": ("Remaining_Life", "remaining_life"),
}


def read_metadata(path: str | Path) -> pd.DataFrame:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".tsv":
        return pd.read_csv(path, sep="\t")
    if path.suffix.lower() != ".csv":
        raise ValueError(f"Unsupported metadata format: {path.suffix}")
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin1"):
        for sep in (",", "\t"):
            try:
                frame = pd.read_csv(path, encoding=encoding, sep=sep)
                if len(frame.columns) > 1:
                    return frame
            except Exception:
                pass
    raise ValueError(f"Unable to parse {path}")


class MetadataCatalog:
    def __init__(self, dataframe: pd.DataFrame, key_column: str | None = None):
        if dataframe.empty:
            raise ValueError("Metadata table is empty")
        self._df = dataframe.copy()
        self.key_column = key_column or self._column("sample_id")
        if not self.key_column:
            raise ValueError("Metadata must contain Id")
        self._df["__sample_id"] = self._df[self.key_column].map(id_text)
        if self._df["__sample_id"].duplicated().any():
            raise ValueError("Duplicate sample IDs")
        self._df.set_index("__sample_id", drop=False, inplace=True)

    @classmethod
    def from_file(
        cls, path: str | Path, key_column: str | None = None
    ) -> "MetadataCatalog":
        return cls(read_metadata(path), key_column)

    def _column(self, field: str) -> str | None:
        lookup = {str(c).lower(): str(c) for c in self._df.columns}
        for candidate in ALIASES.get(field, (field,)):
            if candidate.lower() in lookup:
                return lookup[candidate.lower()]
        return None

    def get(self, sample_id: str | int) -> SampleMetadata:
        key = id_text(sample_id)
        if key not in self._df.index:
            raise KeyError(sample_id)
        row = self._df.loc[key].drop(labels=["__sample_id"])
        return SampleMetadata.from_mapping(row.to_dict())

    def raw(self, sample_id: str | int) -> dict[str, Any]:
        key = id_text(sample_id)
        if key not in self._df.index:
            raise KeyError(sample_id)
        return {
            str(k): clean_value(v)
            for k, v in self._df.loc[key].drop(labels=["__sample_id"]).to_dict().items()
        }

    def search(
        self,
        filters: Mapping[str, Any] | None = None,
        limit: int | None = 100,
        visible_only: bool = False,
    ) -> list[SampleMetadata]:
        frame = self._df
        criteria = dict(filters or {})
        if visible_only:
            criteria.setdefault("visible", True)
        for field, expected in criteria.items():
            column = self._column(field) or (field if field in frame.columns else None)
            if not column:
                raise KeyError(f"Unknown metadata field: {field}")
            expected_values = (
                expected if isinstance(expected, (list, tuple, set)) else [expected]
            )
            allowed = {_compare(v) for v in expected_values}
            frame = frame[frame[column].map(_compare).isin(allowed)]
        if limit is not None:
            if int(limit) < 0:
                raise ValueError("limit must be non-negative or None")
            frame = frame.head(int(limit))
        return [
            SampleMetadata.from_mapping(row.drop(labels=["__sample_id"]).to_dict())
            for _, row in frame.iterrows()
        ]

    def list_datasets(self) -> list[dict[str, Any]]:
        dataset, name = self._column("dataset_id"), self._column("name")
        cols = [c for c in (dataset, name) if c]
        if not cols:
            return [{"dataset_id": None, "name": None, "samples": len(self)}]
        grouped = (
            self._df.groupby(cols, dropna=False).size().reset_index(name="samples")
        )
        return [
            {
                "dataset_id": clean_value(r[dataset]) if dataset else None,
                "name": clean_value(r[name]) if name else None,
                "samples": int(r["samples"]),
            }
            for _, r in grouped.iterrows()
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "samples": len(self),
            "datasets": len(self.list_datasets()),
            "columns": [str(c) for c in self._df.columns if c != "__sample_id"],
            "tasks": {
                task: (
                    len(self.search({task: True}, limit=None))
                    if self._column(task)
                    else 0
                )
                for task in ("fault_diagnosis", "anomaly_detection", "remaining_life")
            },
        }

    @property
    def df(self) -> pd.DataFrame:
        return self._df.drop(columns=["__sample_id"])

    def query(self, query_str: str) -> pd.DataFrame:
        return self.df.query(query_str)

    def keys(self) -> list[str]:
        return list(self._df.index.astype(str))

    def __getitem__(self, key: str | int) -> dict[str, Any]:
        return self.raw(key)

    def __contains__(self, key: object) -> bool:
        return id_text(key) in self._df.index

    def __len__(self) -> int:
        return len(self._df)

    def items(self) -> Iterator[tuple[str, dict[str, Any]]]:
        for key in self.keys():
            yield key, self.raw(key)

    def values(self) -> list[dict[str, Any]]:
        return [value for _, value in self.items()]


class MetadataAccessor(MetadataCatalog):
    """Compatibility API used by PHM-Vibench."""

    def get(self, sample_id: str | int, default: Any = None) -> Any:
        try:
            return self.raw(sample_id)
        except KeyError:
            return default


def smart_read_csv(path: str | Path, auto_detect: bool = True) -> pd.DataFrame:
    del auto_detect
    return read_metadata(path)


def _compare(value: Any) -> Any:
    value = clean_value(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "y", "on"}:
            return True
        if text in {"false", "no", "n", "off"}:
            return False
        try:
            num = float(text)
            return int(num) if num.is_integer() else num
        except ValueError:
            return text
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value
