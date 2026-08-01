# phm-data-factory

> 配置三入口：`--config <path>` ≡ `PHM_DATA_CONFIG=<path>` > CLI args（散落 `IOTDB_*` **不**入此链）
> 中文入口：[快速开始](docs/QUICKSTART_ZH.md) · [接入指南](docs/INTEGRATION_GUIDE.md) · [示例](examples/README.md) · [IoTDB 指南](docs/IOTDB_GUIDE.md)

从 PHM-Vibench 抽取的独立、只读优先的 PHM 数据层。运行时主线是 Apache IoTDB：CLI、Python、MCP 工具查询同一棵 IoTDB 树，Agent 进程内不再依赖本地 `metadata.xlsx` 或 HDF5 缓存。

## 边界

`phm-data-factory` 负责：IoTDB 元数据查找、信号随机访问、样本验证、JSON CLI、只读 Agent 工具。
PHM-Vibench 保留：数据集切分、PyTorch Dataset/DataLoader、任务策略、模型、训练器。

Legacy `metadata.xlsx/CSV + HDF5` 仅用于一次性迁移进 IoTDB。

## 我该看哪个入口

| 目标 | 入口 |
|---|---|
| 10 分钟跑通 | [docs/QUICKSTART_ZH.md](docs/QUICKSTART_ZH.md) |
| 配置、导入、MCP、故障排查 | [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md) |
| Python 读写 IoTDB 示例 | [examples/iotdb_python_read_write.ipynb](examples/iotdb_python_read_write.ipynb) |
| benchmark 接入与工业优化 | [docs/BENCHMARK_INTEGRATION.md](docs/BENCHMARK_INTEGRATION.md) |
| IoTDB 启动与验收 | [docs/IOTDB_GUIDE.md](docs/IOTDB_GUIDE.md) |
| PHMFactory v0.3.1 governed integration | [docs/PHMBENCH_INTEGRATION.md](docs/PHMBENCH_INTEGRATION.md) |

## 安装

```bash
pip install -e '.[yaml,agent]'        # 主安装（YAML 配置 + MCP）
pip install -e '.[legacy]'            # 仅迁移旧本地文件时
```

## 快速开始（两条路）

### 路 A：local 立即起步（数据已在本地）

```bash
cp config/phm-data.sample.yaml config/phm-data.yaml
# 编辑 config/phm-data.yaml：填 metadata_path / signal_path（WSL2 用 /mnt/e/...，勿用 E:\）
phm-data --config config/phm-data.yaml summary
phm-data --config config/phm-data.yaml datasets
```

### 路 B：IoTDB（运行时主线）

1. **启动 IoTDB**（二选一）：
   - docker：`cd docker/iotdb && docker compose up -d`
   - WSL2 直跑二进制（绕过 docker-proxy，详见 [IoTDB 指南](docs/IOTDB_GUIDE.md)）：`sbin/start-standalone.sh`
2. **自检 + 导入**：
   ```bash
   phm-data-iotdb check                                       # 连通自检（含 socket 探测）
   phm-data-iotdb import --config config/phm-data.yaml --report import-report.json
   ```
3. **切到 IoTDB 后端**：编辑 `config/phm-data.yaml` 改 `backend: iotdb`（删 `metadata_path`/`signal_path` 走纯 IoTDB；保留则混合模式）

## 配置查找链

三个入口（`phm-data` / `phm-data-mcp` / `phm-data-iotdb`）共享：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `--config <path>` | 显式指定 RepositoryConfig 文件（YAML/JSON） |
| 2 | `PHM_DATA_CONFIG` env | 指向配置文件（压过 CLI flag，与 `--config` 同级） |
| 3 | CLI 参数 | `--host/--port/--metadata/--signals/...`（默认或显式） |

> 散落 `IOTDB_*` / `PHM_DATA_BACKEND` 等单项 env **不入此链**——只有 `--config` 与 `PHM_DATA_CONFIG` 会。这样设 `IOTDB_HOST`（为 import）不会让 `phm-data --metadata x` 静默丢弃 `--metadata`。细节见 [接入指南](docs/INTEGRATION_GUIDE.md)。

## 查询

CLI（全 JSON 输出）：

```bash
phm-data --config config/phm-data.yaml summary
phm-data --config config/phm-data.yaml window 1 --start 0 --end 12000 --channels 0,1 --max-points 1024
phm-data --config config/phm-data.yaml metadata 1
```

Python（Agent/MCP 默认使用 benchmark-safe 公共视图）：

```python
from phm_data_factory import connect_agent

with connect_agent("config/phm-data.yaml") as tools:
    print(tools.search_samples(task="fault_diagnosis", limit=10))
```

一行接入（v0.2 稳定后端契约，见 [docs/API_CONTRACT.md](docs/API_CONTRACT.md) + [docs/IOTDB_BACKEND.md](docs/IOTDB_BACKEND.md)）：

```python
from phm_data_factory import connect

with connect("config/phm-data.yaml") as repo:   # local 与 iotdb 后端同一抽象
    rows = repo.search_samples({"name": "RM_001_CWRU"}, limit=10)
    x    = repo.read_signal("1", 0, 4096, channels=[0, 1])   # ndarray，不降采样
    # 仅 iotdb 后端可写（HDF5 只读）：
    repo.write_sample("new_id", x, metadata=rows[0], mode="error")
```

`backend: iotdb` 且省略 `metadata_path` 时，元数据从 IoTDB 的 `.meta` 设备读，**换机不再需要本地 `metadata.xlsx`**。新增任务标志 `digital_twin_prediction`（生成式 benchmark 可按列过滤）。

IoTDB 路径布局：

```text
root.vibench.<dataset>.sample_<Id>.signal.ch_<channel>
root.vibench.<dataset>.sample_<Id>.meta.<field>
```

时间戳是样本索引 `0..L-1`，通道对齐；metadata 镜像在时间戳 0，支持纯 IoTDB Agent 配置。

## 导入（一次性，迁 IoTDB）

```bash
phm-data-iotdb import --config config/phm-data.yaml --report import-report.json
# --metadata/--signals 可选：未传时从 config 的 metadata_path/signal_path 读
# --sample-id <id> 指定单样本试导；--continue-on-error 全量容错；--chunk-size 控制批次
```

`--report` 生成 v2 `data_manifest`，包含路径无关的 `dataset_identity` / `dataset_digest`、source hashes 与 imported/failed ids。

默认导入会完整计算源文件 SHA-256。大数据集可先计算一次并复用，或显式选择快速模式：

```bash
phm-data-iotdb source-manifest --config config/phm-data.yaml --output source-manifest.json
phm-data-iotdb import --config config/phm-data.yaml \
  --source-manifest source-manifest.json --report import-report.json

# 明确接受 provenance 不完整时才使用；报告中的 dataset_digest 为 null
phm-data-iotdb import --config config/phm-data.yaml \
  --skip-source-manifest --report fast-import-report.json
```

`--source-manifest` 与 `--skip-source-manifest` 互斥；快速模式不会伪造 dataset identity。

已有 IoTDB 信号可仅补元数据，不重写 93GB 波形：

```bash
phm-data-iotdb sync-metadata --config config/phm-data.yaml --report metadata-sync.json
```

## check 返回码

| 码 | 含义 |
|---|---|
| 0 | 连通（RPC 端口开 + Session 登录成功） |
| 2 | 异常（如 import 校验失败、未捕获错误） |
| 3 | 未连通：RPC 端口不通，或端口开但 Session 失败（JSON 含 `error` 字段） |

`check` 先 socket 探测端口（**无需 apache-iotdb 客户端**即可先探），再测 Session 登录。程序化判定：`phm-data-iotdb check || echo "IoTDB 未就绪"`。

## MCP

```bash
phm-data-mcp --config config/phm-data.yaml
```

Client 配置（Claude Desktop / Cursor 等 MCP client）：

```json
{
  "mcpServers": {
    "phm-data": {
      "command": "/absolute/path/to/venv/bin/phm-data-mcp",
      "args": ["--config", "/absolute/path/config/phm-data.yaml"]
    }
  }
}
```

只读工具：`repository_summary` / `list_datasets` / `search_samples` / `get_sample_metadata` / `get_signal_window` / `get_signal_statistics` / `validate_sample`。

## Skills

- `skills/iotdb`：IoTDB 连接知识包（SessionPool/迭代器铁律、Tree/Table SQL 手册、多语言样板）+ `scripts/validate_connection.py`（连通自检）+ `performance_test.py`（性能基线）
- `skills/tsfile`：TsFile 离线文件读写知识（四语言 API、CSV→tsfile 转换/校验）

`.claude/skills/{iotdb,tsfile}/SKILL.md` 已注册为 Claude 可发现 skill。

> skills 是**知识包 + 自检工具**，不替代 MCP/CLI/AgentDataTools 的数据通道。tsfile 离线装载经评估**不接入** factory tree 链（table/tree schema 不匹配），详见 [接入指南](docs/INTEGRATION_GUIDE.md) 第四节。

## PHMFactory 桥接

本仓库只提供稳定 provider contract，不再内嵌会漂移的 consumer overlay。PHMFactory v0.3.0 明确不集成该 backend；v0.3.1 通过组织仓库、immutable gitlink 和 bounded adapter PR 接入。详见 [PHMBENCH_INTEGRATION.md](docs/PHMBENCH_INTEGRATION.md)。

## 文档导航

| 文档 | 内容 |
|---|---|
| [QUICKSTART_ZH.md](docs/QUICKSTART_ZH.md) | 中文 10 分钟上手 |
| [INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md) | **接入主指南**：配置链、import、tsfile 结论、R00 接入、故障排查 |
| [API_CONTRACT.md](docs/API_CONTRACT.md) | **v0.2 稳定后端契约**：connect + 4 op + 分级 + 弃用策略 |
| [IOTDB_BACKEND.md](docs/IOTDB_BACKEND.md) | **IoTDB 后端开发指南**：connect / read_signal / write_sample / 直接 store |
| [BENCHMARK_INTEGRATION.md](docs/BENCHMARK_INTEGRATION.md) | **benchmark 接入 + 工业优化**：8 环节+缺口、Python 3 姿态、在线/离线瓶颈与优化 |
| [IOTDB_GUIDE.md](docs/IOTDB_GUIDE.md) | IoTDB 启动（docker / WSL2 直跑）+ 四阶段验收 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 数据流架构 |
| [GOAL.md](docs/GOAL.md) | 项目目标与边界 |
| [PHMBENCH_INTEGRATION.md](docs/PHMBENCH_INTEGRATION.md) | PHMFactory v0.3.1 治理接入契约 |
| [VALIDATION.md](docs/VALIDATION.md) | 版本验证范围 |

配置模板：[config/phm-data.sample.yaml](config/phm-data.sample.yaml) · [examples/phm-data.iotdb.yaml](examples/phm-data.iotdb.yaml) · [examples/phm-data.local.yaml](examples/phm-data.local.yaml)

示例导航：[examples/README.md](examples/README.md)

## 测试与构建

```bash
pytest
python -m pip wheel --no-deps --no-build-isolation .
```
