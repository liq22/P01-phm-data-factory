# Session Handoff: data-factory 三仓数据后端集成

**Date:** 2026-07-21 11:41 CST
**Project:** P01-phm-data-factory（同时涉及 PHM-Vibench 与 phm-agent-benchmark）

## Current State

- Task: 让 `P01-phm-data-factory` 成为 PHM-Vibench 和 phm-agent-benchmark 的统一、可复现数据后端，并完成验收和 PR 发布。
- Phase: 实现、三仓验收、公开化、分支推送和 Draft PR 均已完成；等待评审与后续合并决策。
- Progress:
  - data-factory：`feat/iotdb-v02-store-contract`，HEAD `a9bf81b`，已推送。
  - PHM-Vibench：`feat/phm-data-factory-v02-backend`，HEAD `84605c0`，已推送。
  - phm-agent-benchmark：`feat/phm-data-factory-v02-contract`，HEAD `f2400e7`，已推送。
  - 三个工作区在写本交接前均无代码改动；本交接文件自身尚未提交。

## What Was Done

### P01-phm-data-factory

- 将本地文件与 IoTDB 数据访问统一到 typed `0.2` store contract。
- 增加 contract/identity、IoTDB store 分层实现、CLI/config/repository 连接及验证测试。
- Agent 数据面只暴露受限的只读 `AgentDataTools`/MCP：summary → structured search → metadata → statistics → bounded window → validation。
- 不向 Agent 暴露任意 Pandas 查询、无限制 IoTDB SQL、原始 HDF5 handle 或会修改存储的 IoTDB import。
- 增加 PHM-Vibench 与 agent benchmark 的集成文档、验收记录和可重放 consumer patches。
- 仓库在用户获知完整代码、Git 历史、现有 PR 和 Actions 记录会永久公开后，经用户明确授权由 private 改为 public；匿名 HTTPS 访问已验证。

Relevant commits:

- `f385942` — promote IoTDB backend to v0.2 store contract
- `5580faf` — provider release commit；两个消费者精确 pin 此提交
- `8430bf0` — export consumer integration patches
- `0e6b25d` — record cross-repository acceptance
- `a9bf81b` — refresh acceptance against current consumer revisions

### PHM-Vibench

- 新增可选 `phm_data` training backend、配置 schema、provider bridge、文档和测试。
- 通过 public HTTPS submodule `packages/phm-data-factory` 精确 pin `5580fafec2ea5615f6d3276d95e1e5a948cc0f13`。
- 现有 backend 和 `python main.py --config ...` 入口不变；新 backend 必须显式选择并提供 `phm_data_config`，无静默 fallback。
- 文档把该 backend 标记为 experimental，不声称已支持 live IoTDB、性能或多模态。
- `scripts/validate_docs.py` 现在识别 `.gitmodules` 中声明的 submodule，避免初始化 submodule 后误扫其内部文档。

### phm-agent-benchmark

- `src/phm_data_factory` 精确 pin 同一 provider 提交 `5580faf...`。
- topology/contract validator 检查 gitlink、public HTTPS URL、import origin 和可执行 provider contract，失败时 fail closed。
- agent benchmark 不依赖 PHM-Vibench runtime；两个消费者仅共享 provider contract。
- Agent 侧维持 bounded、read-only 数据访问边界。

## Decisions and Rationale

- 统一 provider，而不是让两个 benchmark 互相依赖：减少耦合，并允许独立发布和回滚。
- 使用精确 gitlink，而不是 floating branch/tag：保证消费者运行的是经过验收的同一实现。
- provider 公开且 submodule 使用 public HTTPS：PHM-Vibench 用户可匿名初始化依赖。
- provider API 对 Agent 采用结构化、有限窗口、只读工具：防止任意查询和存储变更进入 benchmark agent surface。
- 三个 PR 默认保持 Draft；本会话未合并、未标记 Ready，也未请求 reviewer/label。
- `v0.2.0` 仅在本地存在，指向 `5580faf`；按既定发布顺序，provider PR 合并前不推送远端标签。

## Pull Requests

- data-factory: [PR #4 — feat: release shared benchmark data backend v0.2](https://github.com/liq22/P01-phm-data-factory/pull/4)
  - `OPEN`, `Draft`, base `main`, head `feat/iotdb-v02-store-contract`, SHA `a9bf81b`
  - PR body 已回链两个 consumer PR。
- PHM-Vibench: [PR #82 — feat(data): add phm-data-factory training backend](https://github.com/PHMbench/PHM-Vibench/pull/82)
  - `OPEN`, `Draft`, base `main`, head `feat/phm-data-factory-v02-backend`, SHA `84605c0`
  - 截至 2026-07-21，4 个 GitHub Actions checks 全部 `SUCCESS`。
- phm-agent-benchmark: [PR #5 — feat(data): pin executable continuous provider contract](https://github.com/liq22/phm-agent-benchmark/pull/5)
  - `OPEN`, `Draft`, base `master`, head `feat/phm-data-factory-v02-contract`, SHA `f2400e7`
- PR #4 和 #5 当前没有配置/返回 GitHub status checks；这不等同于未做本地验收。

## Changed Paths

### P01-phm-data-factory

- Provider contract and safe agent surface: `src/phm_data_factory/contract.py`, `identity.py`, `agent.py`, `mcp_server.py`, `repository.py`
- IoTDB backend: `src/phm_data_factory/stores/iotdb/`, `src/phm_data_factory/iotdb.py`
- Configuration/API: `src/phm_data_factory/config.py`, `cli.py`, `models.py`, `metadata.py`, `pyproject.toml`
- Documentation: `docs/API_CONTRACT.md`, `docs/IOTDB_BACKEND.md`, `docs/BENCHMARK_INTEGRATION.md`, `docs/PHMBENCH_INTEGRATION.md`, `docs/VALIDATION.md`
- Consumer artifacts: `integration/consumer_patches/`, `integration/phm_vibench/`
- Tests: `tests/test_contract_v02.py`, `tests/test_api_contract.py`, `tests/test_iotdb*.py`, `tests/test_digital_twin_prediction.py`

### PHM-Vibench branch

- `.gitmodules`, `packages/phm-data-factory`
- `src/data_factory/phm_data_factory.py`, `src/data_factory/standalone.py`, `src/data_factory/data_factory.py`
- `src/config_schema/models.py`, `src/configs/config_utils.py`
- `docs/phm_data_factory.md`, `KNOWN_LIMITATIONS.md`, `docs/index.md`
- `test/test_phm_data_factory_backend.py`, `test/test_validate_docs_scope.py`, `scripts/validate_docs.py`

### phm-agent-benchmark branch

- `src/phm_data_factory`
- `src/S03_Scripts/validate_data_contract.py`, `validate_submodule_topology.py`
- `src/phm_agent_benchmark/agent/data_source.py`, `runner/preview.py`, `operators/reference_preview.py`
- `src/S04_Tests/test_data_factory_v02_integration.py`, `test_benchmark_runner.py`
- `src/S02_Configs/agent_env/`, `paper/paper.yaml`, `src/README.md`

## Verification

### data-factory (`conda` env `LQ_signal`)

- Full tests: **67 passed, 1 skipped** in 1.34 s；skip 为需要 `PHM_IOTDB_LIVE=1` 的 live IoTDB test。
- `python -m compileall -q src`: **PASS**。
- Wheel build: **PASS**, `phm_data_factory-0.2.0-py3-none-any.whl`。

### PHM-Vibench (`LQ_signal`, Python 3.10, PyTorch Lightning 2.3.3)

- Full `test/`: **132 passed, 1 skipped, 10 warnings** in 8.47 s；skip 为 CUDA-only，warnings 为依赖弃用/NVML。
- Focused backend/docs tests: **5 passed**。
- Docs validator: **PASS**, 115 files scanned。
- Config validator: **PASS**, 7/7 configs。
- Config atlas regeneration: **PASS**, no diff。
- Offline dummy one-epoch smoke: **PASS**。
- GitHub PR #82 CI: Docs/config contracts、Pipeline 06 shell contract、UXFD focused contract、Offline config-first smoke 均 **SUCCESS**。

### phm-agent-benchmark

- Full suite: **191 tests passed** in 28.483 s。
- Topology validator: **PASS**；精确检查 gitlink、URL 与 import origins。
- Provider contract validator: **PASS**, status `compatible_with_gates`。

### Cross-repository

- consumer patch 在 PHM-Vibench 当前 base `a331769` 的全新 clone 上 `git am` 成功，结果 tree 与 `84605c0` 完全一致。
- 从远端 PHM-Vibench feature branch 做全新匿名 shallow clone 后，目标 submodule 成功检出精确 gitlink `5580faf...`。
- provider 仓库当前仍为 `PUBLIC`。
- 截至 2026-07-21 11:41 CST，远端不存在 `v0.2.0` tag。

## Blockers and Open Questions

- 无代码实现 blocker；等待三个 Draft PR 的评审与合并授权。
- live IoTDB 未执行，因为没有配置 `PHM_IOTDB_LIVE=1` 的真实服务；不能据此声称线上连接已验收。
- 多模态支持和性能没有验收或声明。
- PR #4/#5 没有远端 CI checks，需要决定是否仅依赖已记录的本地验收，或在合并前补 Actions。
- 当前环境中普通沙箱执行 `gh auth status` 可能因网络限制误报 token invalid；带网络权限的复核显示 `liq22` keyring 登录有效。不要读取或记录 token。
- `.codex/handoffs/` 为只读，因此本交接保存在 `docs/handoffs/`。

## Next Steps

1. [ ] 先读取本文件和仓库 `AGENTS.md`，再只读复核三个 PR 的 reviews、comments、checks 和 Draft 状态。
2. [ ] 如有 review threads 或 CI failure，分别按 GitHub review/CI 工作流处理并重新验收。
3. [ ] 获得明确授权后，优先 review/merge provider PR #4；本交接不构成 merge 授权。
4. [ ] provider PR 合并后，再确认发布策略并推送本地 annotated tag `v0.2.0`；推送前核对 tag 仍指向 `5580faf`。
5. [ ] 再处理 PHM-Vibench PR #82 和 agent benchmark PR #5 的 Ready/merge；不要假设 Draft 可自动转 Ready。
6. [ ] 若提供真实 IoTDB 环境，执行 opt-in live test 并把命令、配置来源和结果补入验证文档；否则继续明确标注未验证。
7. [ ] 仅在用户要求时提交本交接文件；不要顺带提交其他并发或用户改动。

## Files to Review

- `docs/API_CONTRACT.md`
- `docs/IOTDB_BACKEND.md`
- `docs/BENCHMARK_INTEGRATION.md`
- `docs/VALIDATION.md`
- `src/phm_data_factory/contract.py`
- `src/phm_data_factory/agent.py`
- `src/phm_data_factory/mcp_server.py`
- `src/phm_data_factory/stores/iotdb/store.py`
- `integration/consumer_patches/README.md`
- `integration/consumer_patches/0001-phm-vibench-data-backend.patch`
- `integration/consumer_patches/0002-phm-agent-benchmark-data-contract.patch`
