"""Digital_Twin_Prediction support: model parse, catalog search/summary, agent alias."""
from __future__ import annotations

import pandas as pd

from phm_data_factory import AgentDataTools, PHMDataRepository
from phm_data_factory.metadata import MetadataCatalog
from phm_data_factory.models import SampleMetadata


def _catalog() -> MetadataCatalog:
    df = pd.DataFrame(
        [
            {"Id": 1, "Name": "RM_001_CWRU", "Digital_Twin_Prediction": 1, "Fault_Diagnosis": 0},
            {"Id": 2, "Name": "RM_001_CWRU", "Digital_Twin_Prediction": 0, "Fault_Diagnosis": 1},
            {"Id": 3, "Name": "RM_001_CWRU", "Digital_Twin_Prediction": 1, "Fault_Diagnosis": 0},
        ]
    )
    return MetadataCatalog(df)


def test_sample_metadata_parses_digital_twin_prediction():
    rec = SampleMetadata.from_mapping(
        {"Id": 1, "Name": "X", "Digital_Twin_Prediction": 1}
    )
    assert rec.digital_twin_prediction is True
    # it is a known field now, not dumped into extra
    assert "Digital_Twin_Prediction" not in rec.extra
    assert "digital_twin_prediction" not in rec.extra


def test_sample_metadata_parses_false_and_absent():
    false_rec = SampleMetadata.from_mapping({"Id": 2, "Digital_Twin_Prediction": 0})
    assert false_rec.digital_twin_prediction is False
    absent = SampleMetadata.from_mapping({"Id": 3})
    assert absent.digital_twin_prediction is None


def test_to_dict_round_trips_digital_twin_prediction():
    rec = SampleMetadata.from_mapping(
        {"Id": 7, "Digital_Twin_Prediction": 1}
    )
    dumped = rec.to_dict()
    assert dumped["digital_twin_prediction"] is True


def test_catalog_search_filters_digital_twin_prediction():
    cat = _catalog()
    hits = cat.search({"digital_twin_prediction": True}, limit=None)
    assert {r.sample_id for r in hits} == {"1", "3"}


def test_catalog_summary_counts_digital_twin_prediction():
    tasks = _catalog().summary()["tasks"]
    assert tasks["digital_twin_prediction"] == 2
    # existing task flags still counted
    assert tasks["fault_diagnosis"] == 1


def test_agent_task_alias_digital_twin():
    repo = PHMDataRepository(_catalog(), object())  # search path needs no signal store
    tools = AgentDataTools(repo)
    rows = tools.search_samples(task="digital_twin", limit=None)
    assert {r["sample_id"] for r in rows} == {"1", "3"}
    rows2 = tools.search_samples(task="digital_twin_prediction", limit=None)
    assert len(rows2) == 2
