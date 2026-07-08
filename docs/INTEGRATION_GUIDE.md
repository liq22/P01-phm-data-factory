# phm-data-factory 接入指南

本指南面向**外部 factory（尤其是 R00-phmfactory 的 `data_factory`）**和**本地 agent**，说明如何最方便地接入 phm-data-factory 的 PHM 数据访问层。

运行时后端为 Apache IoTDB；本地查询也支持 local（HDF5）后端用于立即起步或迁移过渡。

---

## 一、配置查找优先级（一次写、到处用）

phm-data / phm-data-mcp / phm-data-iotdb 三个入口共享同一套配置发现链：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `--config <path>` | 显式指定 RepositoryConfig 文件（YAML/JSON） |
| 2 | `PHM_DATA_CONFIG` 环境变量 | 指向配置文件；命中即用文件配置（**压过 CLI flag，与 --config 同级语义**） |
| 3 | CLI 参数 | `--host/--port/--root/--metadata/--signals/...`（默认或显式传入） |

> 三个入口（`phm-data` / `phm-data-mcp` / `phm-data-iotdb`）共享此链。**注意**：散落的 `IOTDB_*` / `PHM_DATA_BACKEND` 等单项 env **不会**触发此链——只有 `--config` 与 `PHM_DATA_CONFIG` 会。这样设 `IOTDB_HOST`（为 import）不会让 `phm-data --metadata x` 静默丢弃 `--metadata`。散落 env 仅当 Python 直接调用 `RepositoryConfig.from_environment()` 时生效。

---

## 二、接入四步流程

### 步骤 1：IoTDB 连通自检

```bash
phm-data-iotdb check                     # 含 socket 端口探测（无需 apache-iotdb 客户端即可先探端口）
phm-data-iotdb check --config config/phm-data.yaml
```

成功输出：`{"host": "127.0.0.1", "port": 6667, "rpc_port_open": true, "connected": true}`，返回码 0。

| 返回码 | 含义 |
|---|---|
| 0 | 连通（RPC 端口开 + Session 登录成功） |
| 2 | 异常（如 import 校验失败、未捕获错误） |
| 3 | check 未连通：RPC 端口不通，或端口开但 Session 失败；JSON 额外含 `error` 字段 |

程序化判定：`phm-data-iotdb check || echo "IoTDB 未就绪"`。

更深入的自检（REST/Java/并发维度，可选）：

```bash
python skills/iotdb/scripts/validate_connection.py --json
```

### 步骤 2：配置 `config/phm-data.yaml`

拷贝 `config/phm-data.sample.yaml`，填入真实路径（**必须 WSL2 形式 `/mnt/e/...`，写 `E:\` 会解析失败**）：

```yaml
backend: local                            # 起步用 local；导入后改 iotdb
metadata_path: /mnt/e/D01_vibench/metadata.xlsx
signal_path: /mnt/e/D01_vibench
default_max_points: 4096
iotdb:                                    # import 与 iotdb 查询共用
  host: 127.0.0.1
  port: 6667
  user: root
  password: root
  root: root.vibench
  fetch_size: 5000
  zone_id: UTC
```

> **陷阱**：`backend: iotdb` 时若保留 `metadata_path`，会走混合模式（metadata 读本地文件、signal 读 IoTDB）；**删掉** `metadata_path`/`signal_path` 才是纯 IoTDB（QUICKSTART 主线）。

### 步骤 3：导入数据到 IoTDB（一次性，迁 iotdb 阶段）

```bash
phm-data-iotdb import --config config/phm-data.yaml --report import-report.json
# --metadata/--signals 现在可选：未传时从 config 的 metadata_path/signal_path 读
```

`--report` 生成的 `data_manifest`（schema_version / root / signal_path_pattern / source hashes / imported/failed sample_ids）可作论文证据链。

### 步骤 4：接入数据访问层（三选一）

```bash
# (a) JSON CLI（人/shell agent）
phm-data --config config/phm-data.yaml summary
phm-data --config config/phm-data.yaml window 1 --start 0 --end 1024 --max-points 128

# (b) MCP server（Claude Desktop / Cursor 等任意 MCP client）
phm-data-mcp --config config/phm-data.yaml

# (c) Python API（R00 factory / 训练侧）
```

```python
from phm_data_factory import AgentDataTools, RepositoryConfig, build_repository
config = RepositoryConfig.from_mapping({"backend": "iotdb", "iotdb": {"root": "root.vibench"}})
with build_repository(config) as repo:
    tools = AgentDataTools(repo)
    print(tools.repository_summary())
```

环境变量注入（phmbench 自动化推荐）：

```bash
export PHM_DATA_CONFIG=/abs/path/to/config/phm-data.yaml
phm-data summary        # 无需 --config
```

### （可选）性能基线

```bash
python skills/iotdb/scripts/performance_test.py --json   # 输出 records/sec、ops/sec、success_rate
```

---

## 三、R00-phmfactory 接入要点

R00 的 `src/data_factory`（`build_data()`）是训练侧 factory，当前用 local/HDF5（`configs/local/local.yaml`）。接入 phm-data-factory 的两条路：

- **读侧（只读查询）**：R00 设 `PHM_DATA_CONFIG` 指向本仓库的 `config/phm-data.yaml`，通过 `AgentDataTools` / MCP / `phm-data` 查询，不改 `build_data()` 契约（符合 `docs/GOAL.md` 的"factory 不得改动"约束）。
- **写侧（数据装载）**：用 `phm-data-iotdb import` 把 `/mnt/e/D01_vibench` 灌入 IoTDB，R00 之后从 IoTDB 读。

> R00 的 `configs/local/local.yaml` 已修正指向 `/mnt/e/D01_vibench`（原 `/mnt/k/...` 盘符不存在）。

---

## 四、tsfile 离线装载：为何**不**用于 factory 加速

曾考虑用 `skills/tsfile` 把 HDF5 批量转成 `.tsfile` 再 `LOAD` 进 IoTDB，以加速 ~93GB 导入。可行性结论如下：

| 维度 | 结论 |
|---|---|
| tsfile Python 绑定 | ✅ `pip install tsfile`（2.1.5 wheel，2025-11 上 PyPI），无需 mvn 编译 |
| IoTDB server 装载 | ✅ SQL `LOAD '/iotdb/data/<subdir>/x.tsfile' autoregister=true`；docker-compose 已挂 `./data:/iotdb/data`，零额外配置 |
| 客户端发起 | ✅ `session.execute_non_query_statement("LOAD '...'")`，factory 现有 apache-iotdb 即可 |
| **⚠️ schema 兼容** | ❌ **硬阻断**：skill 写 table-model（TAG/FIELD），factory 读 tree-model aligned（`root.vibench.<ds>.sample_<id>.signal.ch_<n>`）。同一 `.tsfile` 不能同时满足两种语义——**LOAD 进去的数据 factory 查询读不到** |

**结论**：tsfile 旁路对"加速 factory 导入"目标**走不通**（除非改 factory 到 table model，破坏性；或找到 Python tree-model writer，`skills/tsfile` 未暴露）。

**可选用途**：`scripts/hdf5_to_tsfile.py`（待写）可用 `TsFileTableWriter` 把 HDF5 导出为**独立分析用** `.tsfile`（TAG=sample_id/dataset，FIELD=ch_n），供 Spark/离线分析——但**不接入** factory 的 tree 查询链。

---

## 五、skills 在接入中的角色

- `skills/iotdb`：IoTDB 连接知识包（SessionPool/迭代器铁律、Tree/Table SQL 手册、多语言样板）+ `validate_connection.py`（连通自检）+ `performance_test.py`（性能基线）。本仓库内已通过 `.claude/skills/iotdb` 注册为 Claude 可发现 skill。
- `skills/tsfile`：TsFile 离线文件读写知识（四语言 API、CSV→tsfile 转换/校验）。

skills 是**知识包 + 自检工具**，不是 data-factory 的可执行数据通道（不替代 MCP/AgentDataTools/CLI）。

---

## 六、故障排查

| 现象 | 排查 |
|---|---|
| `Could not connect to (127.0.0.1, 6667)` | `phm-data-iotdb check` 看 `rpc_port_open`；起容器 `cd docker/iotdb && docker compose up -d` |
| local 查询报路径不存在 | 配置里写 `/mnt/e/...`（WSL2），不要写 `E:\` |
| iotdb 查询仍读本地文件 | `backend: iotdb` 时删掉 `metadata_path`（见步骤 2 陷阱） |
| import 报缺 metadata/signals | 传 `--config`，或在命令补 `--metadata/--signals` |

## 相关文档
- [QUICKSTART_ZH.md](QUICKSTART_ZH.md) — 快速开始
- [BENCHMARK_INTEGRATION.md](BENCHMARK_INTEGRATION.md) — benchmark 接入与工业场景优化
- [IOTDB_GUIDE.md](IOTDB_GUIDE.md) — IoTDB 启动与四阶段验收
- [PHMBENCH_INTEGRATION.md](PHMBENCH_INTEGRATION.md) — PHM-Vibench overlay 集成契约
- [GOAL.md](GOAL.md) — 项目目标与边界
- [../examples/README.md](../examples/README.md) — 配置、MCP、notebook 示例导航
