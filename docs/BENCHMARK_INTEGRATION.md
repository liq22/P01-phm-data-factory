# Benchmark 接入与工业场景优化

本文档面向**把 phm-data-factory 接入各种 benchmark**（故障诊断 / RUL / 异常检测 / 生成式）的接入方，以及**真实工业场景的性能优化**。基于代码现状（file:line 证据），分析为主，给出优化路线图。

> 配套：[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)（接入主指南）、[ARCHITECTURE.md](ARCHITECTURE.md)、[GOAL.md](GOAL.md)。PHMFactory v0.3.0 已明确延期该可选 backend；训练 adapter 只在 v0.3.1 的 consumer PR 中维护，本仓库不再分发 overlay。

---

## 1. 目的与边界

data-factory 是**只读 PHM 数据访问层**，被 benchmark 与 agent 复用。

| 归属 | 职责 |
|---|---|
| **data-factory** | IoTDB 元数据查找、信号随机访问、样本验证、JSON CLI、只读 Agent 工具 |
| **benchmark** | task 切分（DG/CDDG/FS/...）、PyTorch Dataset/DataLoader、采样器、模型、训练器 |

**硬约束**（`docs/GOAL.md`）：benchmark 的 `build_data()` 训练入口**不变**；PHMFactory v0.3.1 仅通过 bounded registry adapter 接入，Agent benchmark 通过 `AgentDataTools` 或 `AgentDataPort` 接入。

---

## 2. 接入环节清单（8 环节 + 缺口）

| # | 环节 | factory 现状（file:line） | benchmark 侧责任 | 缺口 |
|---|---|---|---|---|
| ① | 配置发现 | `--config` > `PHM_DATA_CONFIG` > CLI args（`config.py:84-94`、`iotdb.py:481-496`）；散落 `IOTDB_*` 不入链 | 设 `PHM_DATA_CONFIG` 或调 `build_agent_data_tools(args.data)` | 配置无 schema 版本号；benchmark `data:` 块与 factory 配置是两套 |
| ② | schema 约定 | IoTDB v2 同时保存检索索引和 typed JSON metadata；`metadata_frame("phm_vibench_v1")` 恢复训练列与标量类型 | 用 `sample_id` 主键对齐；旧库先执行 `sync-metadata` | v1 索引元数据只能降级读取，不能直接训练 |
| ③ | task 语义 | `search_samples(task=fault/anomaly/rul)` + 别名（`agent.py:40-50`）；未知 task 抛错 | 自己跑 DG/CDDG/FS 切分（`task.type`） | **factory task 与 benchmark `task.type` 正交两套**；命名不一致（`rul_prediction` ≠ `remaining_life`） |
| ④ | split | **不做**（`GOAL.md` 明确） | 全权负责 train/val/test + 切域 | 设计正确；`summary()` 不报 split 比例（需 benchmark 文档明示） |
| ⑤ | 性能基线 | `skills/iotdb/scripts/performance_test.py`；`check` 返回码 0/2/3（`iotdb.py:528-581`） | 接入前跑 `phm-data-iotdb check` | 缺基准阈值文档；`summary()` 对 IoTDB 大库慢（`availability_is_cheap=False`，`repository.py:38`） |
| ⑥ | 版本兼容 | 包版本 `0.2.1`；Agent API/capability schema `1.0.0`；DataPort 声明 stream cursor capability | 固定 provider revision 并校验 package/API/capability version | `api_version="0.2"` 仅为兼容别名 |
| ⑦ | 只读契约 | `benchmark_public` 强制 visible-only、标签移除和 bounded window；MCP 固定使用该 profile | evaluator 私有标签由 benchmark 自己持有 | 管理员 import/sync 不进入 Agent 工具面 |
| ⑧ | 离线/在线 | local/IoTDB 都实现 repository；DataPort 提供有界、可恢复的连续序列 cursor | 保留原 split/Dataset/DataLoader | 离散/event 模态与服务端原生流仍是后续 gate |

---

## 3. Python 接入指南

### 三种接入姿态

| 姿态 | 适用 | 入口 |
|---|---|---|
| **CLI 子进程** | 跨语言 / shell agent | `phm-data --config <yaml> <cmd>`（`cli.py:51-127`） |
| **Python 直调 AgentDataTools** | 同进程 metadata/window 工具调用 | `build_repository(config)` + `AgentDataTools(repo, max_points)` |
| **Python 直调 AgentDataPort** | bounded episode、opaque replay 和 cursor 恢复 | `AgentDataPort(AgentDataTools(repo, max_points))` |
| **MCP client** | 外部 LLM agent（Cursor / Claude Desktop） | `phm-data-mcp --config <yaml>`（`examples/mcp-client.json`） |

### 最小代码（Python 直调，推荐）

```python
from phm_data_factory import connect_agent

with connect_agent("config/phm-data.yaml") as tools:
    tools.repository_summary()                              # 轻：盘点覆盖
    tools.search_samples(task="fault_diagnosis", limit=10)  # 轻：结构化检索
    meta = tools.get_sample_metadata("1")                   # 轻：public shape，无 label
    win  = tools.get_signal_window("1", 0, 1024, max_points=512)  # 重：bounded 信号窗口
    stats = tools.get_signal_statistics("1")                # 重：per-channel 统计
```

### Bounded episode 与 replay

```python
from phm_data_factory import AgentDataPort, AgentDataTools, connect

repository = connect("config/phm-data.yaml")
with AgentDataPort(AgentDataTools(repository, 4096)) as data:
    public = data.search_samples({"task": "fault_diagnosis"}, limit=10)
    cursor = data.open_stream(
        {"stream_id": public[0]["sample_id"], "channels": [0], "max_points": 1024}
    )
    window = cursor.next()
```

`AgentDataPort.manifest()` reports package `0.2.1`, schema `1.0.0`, and
`stream_cursor=true`. Registered replay streams expose opaque sample IDs only
after each cursor step releases them.

### 7 方法轻重特征

| 方法 | 读信号？ | 性能 | 备注 |
|---|---|---|---|
| `repository_summary` / `list_datasets` / `search_samples` / `manifest` | 否 | **轻**（metadata-only） | JSON 安全 |
| `get_sample_metadata` / `validate_sample` | 中（contains + shape） | **轻**（IoTDB shape 零 RPC） | |
| `get_signal_window` | **重** | 触发 H5 read 或 IoTDB SELECT | `max_points` 有界（默认 4096） |
| `get_signal_statistics` | **重** | 内部调 window | 默认 `max_points=100000` |

### 训练侧拿全量张量

Agent 层为 JSON 安全做了 `max_points` 有界 + `.tolist()`。**训练时绕过 Agent**，直接用 `PHMDataRepository` + `max_points=None` 拿完整 ndarray（`PHMBENCH_INTEGRATION.md:36-39`）：

```python
with build_repository(config) as repo:   # PHMDataRepository
    window = repo.get_signal_window(sample_id, start, end, channels, max_points=None)
    tensor = window.values   # ndarray (length, n_channels)，无降采样
```

---

## 4. 不同 benchmark 的接入差异

| benchmark | factory task 参数 | 关键 metadata 字段 | 信号读取 | 注意 |
|---|---|---|---|---|
| **故障诊断** | `task="fault_diagnosis"`（别名 `fault`） | `label`、`fault_level`、`domain_id` | window + DG/CDDG 按 `domain_id` 切域 | R00 对应 `task.type=DG/CDDG`，`task.name=classification` |
| **RUL** | `task="rul"`（别名 `remaining_life`） | `rul_label`（IoTDB 存 TEXT，benchmark 自行转 float） | 全寿命退化序列（FEMTO/IMS），`sample_length` 很长；window_size/stride 切窗由 benchmark 做 | factory 只暴露整条 sample 边界，不做窗口化 |
| **异常检测** | `task="anomaly"`（别名 `anomaly_detection`） | `label`（二分类） | **缺口**：`SampleMetadata` 只有 sample 级 label，无点级 anomaly 区间 —— benchmark 自行维护点级标注 | |
| **生成式** | **factory 无原生 task 支持** | 条件采样用 `label`/`domain_id`（factory 有） | 合成数据**不回流** factory（只读），benchmark 自存 `samples.pt` | **缺口**：`Digital_Twin_Prediction` 列不在 `IoTDBImporter.SCHEMA`（`iotdb.py:192-208`），落 `extra` 无法过滤 |

---

## 5. 工业优化 — 在线（训练实时查询）

### 当前瓶颈（8 项，file:line）

| # | 瓶颈 | 证据 |
|---|---|---|
| O1 | **无连接池**，N 训练 worker = N thrift 长连接，无复用/限流 | `iotdb.py:64-92`、`iotdb.py:128-138` |
| O2 | RPC 压缩关闭（`enable_rpc_compression=False`） | `iotdb.py:79` |
| O3 | `todf()` 一次性物化整段窗口，不走迭代器 | `iotdb.py:176` |
| O4 | 降采样在 Python 端切片（`[::step]`），服务端无 `SLIMIT`/`GROUP BY` | `iotdb.py:185`、`repository.py:91-95` |
| O5 | 无重试 / 无超时 / 无断线重连 | `iotdb.py:68-80` |
| O6 | `Session` 跨线程共享 = 非 thread-safe，代码未提示 | `iotdb.py:136-138` |
| O7 | `get_signal_statistics` 默认 `max_points=100000` + `fetch_size=5000` → 多 round-trip | `repository.py:113`、`config.py:23` |
| O8 | 无客户端 LRU，同一 (sample, window) 反复查询全量打 IoTDB | `repository.py:69-110` |

### 优化建议（标注复用 skill 资产 / 改哪个文件）

- **SessionPool 化**（最大收益）：把 `IoTDBSession`（`iotdb.py:64-92`）内部单 Session 改为基于 `queue.Queue` 的池，**直接照搬** `skills/iotdb/assets/connection_templates/python_connection_template.py:368-406` 的 `ConnectionPool` + `session_context`；`IoTDBConfig`（`config.py:17-36`）加 `pool_size` 字段。对调用方零侵入（同名 API）
- **开 RPC 压缩**：`iotdb.py:79` 改 `enable_rpc_compression=True`（或可配置），跨网训练集群收益最大
- **迭代器读 或 服务端降采样**：`iotdb.py:172-185` 的 `read` 改为 (a) 迭代器 `has_next/next` 攒批（参照 skill 模板 `:120-128, 256-323`），或 (b) SQL 带 `SLIMIT`/`GROUP BY` 让服务端降采样，省掉 `step` 倍传输
- **重试包装**：搬 skill 模板 `:408-455` 的 `RobustConnection.connect_with_retry` / `execute_with_retry`，包住 `open()` 与每次 `execute_query_statement`
- **客户端 LRU**：在 `repository.py:get_signal_window` 之上加 `(sample_id, start, end, channels, max_points)` → `SignalWindow` 缓存（`functools.lru_cache` 或 dict+size 上限）
- **fetch_size 可调**：`get_signal_statistics` 这类大窗口场景上调 `fetch_size`（默认 5000 → 20000~50000，配合压缩）
- **并发安全文档**：明确"每 worker 一个 `IoTDBSignalStore` 实例"，或加锁

---

## 6. 工业优化 — 离线（93GB 一次性导入 + 批量分析）

### 当前瓶颈（7 项，file:line）

| # | 瓶颈 | 证据 |
|---|---|---|
| F1 | **导入串行**，`for sample_id in ids` 无并发 | `iotdb.py:289-296` |
| F2 | 整个导入共用 1 条 thrift 连接 | `iotdb.py:210-215` |
| F3 | `chunk_size` 固定 10000，无自适应 / 无 numpy buffer 复用 | `iotdb.py:233, 250-267` |
| F4 | **无离线批读 API**（`read_iter` / `export`），只能逐样本 `read` + `todf` | `iotdb.py:157-185` |
| F5 | `read` 一次性 `todf()` + Python 切片，离线全量统计内存爆炸 | `iotdb.py:176, 185` |
| F6 | `LOAD TSFILE` 旁路被 schema 阻断 | `iotdb.py:248, 316-323`（aligned + ch_* + GORILLA + SNAPPY） |
| F7 | 导入失败无断点续传，只能 `continue_on_error` 整轮重来 | `iotdb.py:290-296` |

### 优化建议

- **并发导入**：`import_repository`（`iotdb.py:289-296`）改 `ThreadPoolExecutor`，每 worker 一个 `IoTDBSession`（池化）。写入 IO 密集，多 session 并发显著压时间；thrift Session 非线程安全 ⇒ 必须 per-thread session（正好对应池模型）
- **chunk_size 自适应**：按 `length × channels × 8B` 推算到 ~16MB/tablet；考虑 `insert_aligned_tablets`（批量提交多 tablet）减 RPC 次数
- **离线批读 API（新方法）**：`IoTDBSignalStore.read_iter(sample_id, ...) -> Iterator[np.ndarray]`，参照 skill 模板 `:291-323` 的 `_stream_process_large_dataset` 按 chunk 流式；`SignalStore` 协议（`stores/base.py`）加默认 `read_iter` 供 local 后端 fallback
- **导出 npz/parquet**：`repository.py` 加 `export_sample(sample_id, dest)`，离线一次写盘、反复读盘，避免反复打 IoTDB
- **断点续传**：用 `data_manifest.imported_sample_ids`（`iotdb.py:434-454`，已自带）做幂等检查，跳过已导入样本
- **LOAD TSFILE 为何不可行**：factory 写 aligned + `ch_*` + GORILLA + SNAPPY（`iotdb.py:316-323`），原始 .h5 导出的 tsfile 必须重打 schema 才能匹配；直接 LOAD 会 `SCHEMA_NOT_MATCH`。详见 [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) 第四节

---

## 7. 防破损设计（factory 升级不破 benchmark）

| 机制 | 现状 | 建议 |
|---|---|---|
| API 版本 | package `0.2.1`，API/capability schema `1.0.0`，旧 `api_version="0.2"` 为兼容别名 | benchmark 启动时校验 package 与两个 schema major |
| `SampleMetadata` schema | 21 字段冻结 + 别名（`models.py:90-208`） | 列入显式稳定契约文档；删/改类型算 breaking |
| consumer 版本 | consumer 通过 immutable gitlink 固定 provider | consumer 启动时校验 package/API schema 与精确 revision |
| 只读契约 | 仅 Agent/MCP 路径只读 | Python `PHMDataRepository` 路径加只读 guard（或文档强约束） |
| 生成式 schema | `Digital_Twin_Prediction` 丢（`iotdb.py:192-208`） | `SCHEMA` 补该字段（BOOLEAN），让生成式 benchmark 可按它过滤 |

---

## 8. 缺口优先级

| 优先级 | 缺口 | 理由 |
|---|---|---|
| **P0** | consumer 启动时执行 manifest compatibility check | provider 已声明 package/API/capability version，consumer 仍需拒绝不兼容 major |
| **P0** | `Digital_Twin_Prediction` 补进 `IoTDBImporter.SCHEMA` | 生成式 benchmark 当前接不进（落 extra 无法过滤） |
| **P1** | SessionPool 化 `IoTDBSession`（复用 skill `ConnectionPool`） | 在线场景最大瓶颈，零侵入改造，skill 资产现成 |
| **P1** | 迭代器读 / 服务端降采样（替代 `todf` 一次性） | 在线 + 离线共用读路径，内存与传输双省 |
| **P2** | 并发导入（`ThreadPoolExecutor` per-session） | 93GB 离线导入耗时，并发是最大杠杆 |
| **P2** | 离线批读 API（`read_iter` / `export_sample`） | 离线批量分析目前只能逐样本物化 |
| **P2** | 断点续传（用 `data_manifest` 幂等） | 大规模导入失败后整轮重来的痛点 |

---

## 相关文档
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) — 接入主指南（配置链 / import / tsfile 结论 / R00 接入）
- [PHMBENCH_INTEGRATION.md](PHMBENCH_INTEGRATION.md) — PHMFactory v0.3.1 治理接入契约
- [ARCHITECTURE.md](ARCHITECTURE.md) — 数据流架构
- [GOAL.md](GOAL.md) — 项目目标与边界（`build_data()` 不变约束来源）
