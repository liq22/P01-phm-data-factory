# Versioned Agent/Benchmark Contract

`phm-data-factory` is an independent data plane. Benchmarks and agents should
consume it through the read-only `AgentDataTools` surface and inspect
`AgentDataTools.manifest()` before use.

## Manifest fields

| Field | Meaning |
|---|---|
| `provider` | Stable provider identifier |
| `package_version` | Installed package release |
| `api_schema_version` | Consumer-contract schema; same major is required |
| `capability_schema_version` | Shape of the capability block |
| `read_only` | Must remain true for the AgentDataTools surface |
| `backend_kind` | Runtime-selected in v1; a run fingerprint should record the concrete backend separately |
| `dataset_digest` | `null` until a configured repository manifest supplies one |
| `capabilities` | Explicit implemented features; absent/future features must not be inferred |
| `compatibility` | Pre-1.0 compatibility and deprecation policy |

Current v1 capabilities are intentionally conservative:

- structured sample search;
- sample description;
- bounded continuous signal windows;
- bounded window statistics;
- sample-index time basis;
- no generic stream cursor;
- no batch-window contract;
- no binary/categorical/event typed window contract yet.

DF-PR2 should add typed signal descriptors and new modalities only together
with compatibility and positive/negative tests.

## Consumer check

```python
from phm_data_factory import AgentDataTools

manifest = AgentDataTools.manifest()
assert manifest["read_only"] is True
assert manifest["api_schema_version"].split(".", 1)[0] == "1"
assert manifest["capabilities"]["bounded_window"] is True
```

A benchmark must fail explicitly when a required capability is false or when
the API schema major differs. It must not silently assume a stream API, label
visibility policy, event modality, or dataset digest.

## Version policy

The package is pre-1.0. API changes should:

1. update the schema version;
2. add compatibility tests and migration notes;
3. keep old fields for at least one minor release when feasible;
4. avoid advertising a capability before its implementation and tests exist.

## Deferred decision

`apache-iotdb` remains a core dependency in this PR. Moving it to an optional
`iotdb` extra requires an import and installation matrix proving that local-only
workflows still function, and therefore belongs in a separate dependency PR.
