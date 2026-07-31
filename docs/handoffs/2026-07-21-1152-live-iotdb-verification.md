# Session Handoff: IoTDB 后端小批量 live 验证

**Date:** 2026-07-21 11:52 CST
**Project:** P01-phm-data-factory
**Branch:** `feat/iotdb-v02-store-contract`（HEAD `a9bf81b`，已推送；工作树干净）
**Companion to:** `docs/handoffs/2026-07-21-1141-three-repo-data-backend.md`（三仓 v0.2 总交接）

## 为什么有这份交接

1141 交接把 *"live IoTDB 未执行"* 列为 open item（Blockers 与 Next Steps #6）。
本会话**执行了那次 opt-in live 验证**，把该状态从"未验证"推进到"小批量通过"，并发现两个后续要处理的点。其余三仓集成/PR/验收状态见 1141，不在此重复。

## Current State

- Task: 对重构后的 IoTDB 后端做真实小批量端到端验证（unit suite 全是 mock，真实 `apache-iotdb` 调用此前未跑过）。
- Phase: 验证完成；IoTDB 仍在运行；代码未改、未提交（HEAD 仍是 `a9bf81b`）。
- Runtime: 一个本地 IoTDB 2.0.8（**二进制直跑**，非 docker）在 `127.0.0.1:6667` 监听，`root.vibench` 下已导入 12 个 RM_016_JNU 样本。

## What Was Done（按 runbook，全部 ✅）

1. **起 IoTDB**：Docker Hub `registry-1.docker.io` 连接超时（拉不到 `apache/iotdb:2.0.8-standalone`）→ 改用 `https://archive.apache.org/dist/iotdb/2.0.8/apache-iotdb-2.0.8-all-bin.zip` 下载二进制到 `<IOTDB_LOCAL_ROOT>/apache-iotdb-2.0.8-all-bin`（123MB），`sbin/start-standalone.sh` 起服务。`phm-data-iotdb check` → `connected:true`。
2. **导入 RM_016_JNU**（最小 h5，12 样本 / 68.7MB）：`imported_count=12, failed_count=0`，10.8s。走新的单写路径 `IoTDBImporter.import_sample → IoTDBSignalStore.write`（真实 `create_aligned_time_series` / `insert_aligned_tablet` / `insert_aligned_record` / `CREATE DATABASE`）。
3. **`verify_metadata`**：`only_in_source=0`、`field_diffs=0`、exit 0。`missing_columns=[digital_twin_prediction, fault_level, rul_label]` 是 RM_016_JNU 源里本就为空的 nullable 字段（`field_diffs=0` 已保证），非缺陷。
4. **真实样本回读**：sample 46995，IoTDB `read_signal` 与 HDF5 源 bit-close 一致（`rtol/atol=1e-9`）—— 证明 iterator read + `Field.get_double_value()` + NaN-fill 在真实库正确。
5. **`get_signal_statistics`**：mean/std/rms 有限。
6. **`digital_twin_prediction=True` 合成往返**：写入 → `load_metadata_from_iotdb` 读回仍 `True`（新 BOOLEAN 字段在真实 IoTDB 持久化）。
7. **合成 write→read→delete 往返**：全通过；delete 后 `contains=False`（真实 `delete_data_in_range(paths, 0, 2**63-1)` + `_drop_metadata` 工作）。
8. **`PHM_IOTDB_LIVE=1 pytest tests/test_iotdb_live.py`**：绿（1 passed）。

诊断/导入脚本（临时，未提交）：`<TMPDIR>/live_diag.py`、`<TMPDIR>/live_smoke.py`、`<TMPDIR>/import_rm016_fast.py`、报告 `<TMPDIR>/import-rm016.json`、`<TMPDIR>/verify-rm016.json`。

## Decisions and Rationale

- **用 archive.apache.org 二进制而非 docker**：Docker Hub 在本机不可达；archive.apache.org 可达（`HTTP/1.1 200 OK`）。结果与 docker 等价（IoTDB 2.0.8 standalone）。
- **导入时绕过 `build_source_manifest`**（`source_manifest=None`）：见下方 Finding #1，否则会对 ~250GB h5 做 sha256 而挂住几十分钟。验证阶段不需要 manifest。
- **read-back 用真实信号而非纯合成**：sample 46995 来自真实 cache.h5，IoTDB 读回与 HDF5 源数值一致——这是 mock 无法证明的等价性。

## Findings（后续要处理）

1. **`build_source_manifest` 是真实可用性瓶颈**（既有代码，逐字搬进 `stores/iotdb/bulk.py`，非本次回归）。
   - `scripts/import_datasets.py` 与 `phm-data-iotdb import` 在导入前会对 signals 目录下**每个** h5 算 sha256：86GB `cache.h5` + 25 个 `RM_*.h5` ≈ 250GB → 几十分钟，阻塞真正导入（首次跑到 10min timeout 被杀，零输出）。
   - 建议修法（择一）：把 manifest hash 改为 opt-in（`--source-manifest`）/ 跳过超过阈值的文件 / 只哈希 manifest 登记 file / 全量导入默认 `None`。**全量导入前必须先处理。**
2. **确认了文档里的 v0.2 限制（非 bug）**：`write_sample` 后用**同一个** repo 的 `read_signal` 读刚写的样本失败（repo catalog 是 connect 时快照）。需 fresh `connect()` 或走 `store`（store 写后失效、下次 lazy 重载）。已在 `docs/API_CONTRACT.md` 写明。live 验证复现了该行为。

## Runtime State（新会话务必知道）

- **IoTDB 仍在运行**（二进制，非容器）：`<IOTDB_LOCAL_ROOT>/apache-iotdb-2.0.8-all-bin`，PID 由 `start-standalone.sh` 守护。停止：`IOTDB_HOME="<IOTDB_LOCAL_ROOT>/apache-iotdb-2.0.8-all-bin" "$IOTDB_HOME/sbin/stop-standalone.sh"`。数据在 `<IOTDB_LOCAL_ROOT>/apache-iotdb-2.0.8-all-bin/data`（standalone 默认）。
- `root.vibench` 下有 **12 个 RM_016_JNU 样本**（真实数据，可用作读回 smoke）。合成测试样本已清掉。
- `config/phm-data.yaml`（gitignored，机器私有）仍为 `backend: local`，指向 `<PHM_VIBENCH_ROOT>`。读 IoTDB 时用 `connect({"backend":"iotdb", ...})` 或临时 `<TMPDIR>` yaml，勿改本地配置。
- Docker Hub 不可达是新会话可能再撞到的网络约束；IoTDB 二进制已落盘可复用。

## Verification

- 本会话**未改任何产品代码**，故 mock 套件仍是 `67 passed, 1 skipped`（与 1141 一致，本会话开始前复核过）。
- live 验证结果见上文 What Was Done；命令与配置来源已记录，可重放。
- 未运行全量导入；未合并/推送/打 tag。

## Blockers and Open Questions

- 全量导入被 Finding #1（manifest sha256 瓶颈）阻塞，需先修。
- 是否要保留运行中的 IoTDB、还是停掉清数据，等用户定。
- 代码当前在 `feat/iotdb-v02-store-contract`，PR #4 仍 Draft（见 1141）——本会话未做合并/发布动作。

## Next Steps

1. [ ] 新会话先读 `docs/handoffs/2026-07-21-1141-three-repo-data-backend.md` 拿三仓全景，再读本文件拿 live 验证细节。
2. [ ] 确认 IoTDB 是否仍在运行（`ss -ltn 'sport = :6667'`）；若不需，按上文命令停服。
3. [ ] 修 Finding #1（`build_source_manifest` 瓶颈）后再决定是否全量导入；全量导入参考 `docs/IMPORT_RUNBOOK.md` 与仓库 README 的 `--all-except RM_005_Ottawa23,RM_006_THU,RM_007_MFPT` 姿态。
4. [ ] 如需把 live 验证写进正式验收文档：把本文件 What Was Done 的命令+结果并入 `docs/VALIDATION.md` / `docs/IOTDB_GUIDE.md`，并把 1141 的 "live IoTDB 未执行" 更新为"小批量已通过；全量未跑"。
5. [ ] 仅在用户要求时提交本交接文件；勿顺带提交其他改动。

## Files to Review

- `src/phm_data_factory/stores/iotdb/store.py`（`read` iterator / `write` / `delete` / `write_metadata`）
- `src/phm_data_factory/stores/iotdb/bulk.py`（`build_source_manifest` — Finding #1 在此）
- `docs/API_CONTRACT.md`（write-then-read 同 repo 限制）
- `docs/handoffs/2026-07-21-1141-three-repo-data-backend.md`（三仓全景）
- `<IOTDB_LOCAL_ROOT>/`（运行中的 IoTDB 实例 + 数据目录）
