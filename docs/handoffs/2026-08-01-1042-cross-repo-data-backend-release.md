# Session Handoff: Shared PHM Data Backend Release

**Date:** 2026-08-01 10:42 CST
**Project:** `PHMbench/phm-data-factory` and its two benchmark consumers

## Current State

- Task: make `phm-data-factory` a convenient, governed backend for PHM-Vibench/PHMFactory and `phm-agent-benchmark`.
- Phase: provider released; both consumer integrations are open and Ready for review.
- Provider authority: public release `v0.2.0`, commit `16180b5fd9ca31d79fe65efd29b11439c1e54186`.
- Consumer PRs:
  - `liq22/phm-agent-benchmark#5`, head `0834ee0b04a0f5abd7a4c3697c955efbf538b0dc`.
  - `PHMbench/PHM-Vibench#148`, head `ea55741d0da618002cba28246618b57de6bbcbdf`.

## What Was Done

- Transferred the provider to `PHMbench/phm-data-factory`, made it public, merged provider PR #4, and published `v0.2.0` with wheel, sdist, and checksums.
- Stabilized the provider API around `connect`, dense `read_signal`, trusted `metadata_frame("phm_vibench_v1")`, and read-only bounded `AgentDataTools`.
- Pinned both consumers to the same canonical HTTPS repository and exact released gitlink.
- Added fail-closed topology, package-version, schema-major, import-origin, and capability validation in the agent benchmark.
- Added a bounded optional `phm_data` adapter in PHMFactory while preserving its existing filtering, split, windowing, Dataset/DataLoader, task, model, and trainer ownership.
- Fixed the agent PR CI so its fresh runner installs the benchmark's declared Agent Gateway requirements before executing the full suite.

## Decisions and Rationale

- The provider owns metadata/storage access; PHMFactory owns training semantics; the agent benchmark owns task, action, evaluator, budget, and trace semantics.
- Consumers pin an immutable commit instead of a branch or floating tag.
- Agent access is read-only and structured: summary → search → metadata → statistics → bounded window → validation. Arbitrary Pandas expressions, unrestricted IoTDB SQL, raw HDF5 handles, and mutating imports are not agent tools.
- Compatibility evidence is reported as `compatible_with_gates`; it is not promoted to a real-dataset, live-backend, multimodal, performance, or paper-result claim.

## Changed Paths

- Provider: `.github/workflows/ci.yml`, `src/phm_data_factory/`, `scripts/`, `docs/`, `tests/`, packaging and release metadata.
- Agent consumer PR #5: `.gitmodules`, `src/phm_data_factory`, contract/topology validators, configs, tests, CI, and governance logs.
- PHMFactory consumer PR #148: `.gitmodules`, `packages/phm-data-factory`, `src/data_factory/phm_data_factory.py`, `src/data_factory/standalone.py`, configs, policy/tests, CI, and integration documentation.

## Verification

- Provider local suite: 76 passed, 1 skipped; compile and wheel build passed.
- Provider synthetic Apache IoTDB 2.0.8 acceptance: one 32×2 sample imported in four chunks; `imported_count=1`, `failed_count=0`; live test and the complete read-only AgentDataTools sequence passed.
- Provider PR #4 CI: Python 3.10/3.13 workflow passed.
- Agent PR #5 local: topology, contract, and project validators passed; unittest 192 passed with 1 skipped; pytest parity 191 passed with 1 skipped and 156 subtests. GitHub Actions CI passed.
- PHMFactory PR #148 local: 242 passed, 1 skipped; 8 focused adapter tests; 9 policy tests; 7/7 configs; docs, CLI, Dummy train/test, wheel, and clean installed-wheel smoke passed.
- PHMFactory PR #148 cloud: all seven workflows passed.
- Anonymous HTTPS `git ls-remote` confirmed public provider access; `main` and peeled `v0.2.0` both resolved to the released commit before this handoff-only documentation commit.

## Blockers and Open Questions

- The two consumer PRs are intentionally not merged; default consumer branches do not use the provider until maintainers merge them.
- PHMFactory release readiness still has five pre-existing unrelated blockers: two missing CWRU hashes, two floating CWRU provider revisions, and package version `0.3.0.dev0`.
- Full private/large-dataset import, the approximately 250 GB workflow, real PHM metrics, throughput, and live IoTDB use from inside PHMFactory remain unverified.
- Provider v0.2.0 declares continuous series and sample-index windows only; stream cursor, binary, categorical, event, and multimodal provider capabilities remain gated.

## Next Steps

1. [ ] Review and merge `liq22/phm-agent-benchmark#5` into `master` after maintainer approval.
2. [ ] Review and merge `PHMbench/PHM-Vibench#148` into `dev` after maintainer approval.
3. [ ] After both merges, re-run each consumer's exact-submodule and installed-package smoke from a clean checkout.
4. [ ] Resolve the five existing PHMFactory release-readiness blockers before cutting its next release.
5. [ ] Run a separately governed real-dataset/large-data acceptance with immutable source manifest, dataset digest, split/leakage audit, command/config/environment records, and bounded performance measurements.
6. [ ] Version and implement stream/multimodal capabilities only when concrete consumer requirements and fixtures exist.

## Files to Review

- `docs/API_CONTRACT.md`
- `docs/PHMBENCH_INTEGRATION.md`
- `docs/BENCHMARK_INTEGRATION.md`
- `AGENTS.md`
- `https://github.com/liq22/phm-agent-benchmark/pull/5`
- `https://github.com/PHMbench/PHM-Vibench/pull/148`
