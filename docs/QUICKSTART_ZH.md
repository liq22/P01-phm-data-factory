# phm-data-factory 中文快速开始

## 目标边界

```text
phm-data-factory
  ├── IoTDB 元数据与信号读取
  ├── 旧 metadata.xlsx / CSV + HDF5 一次性导入
  ├── JSON CLI
  └── 只读 MCP Agent 工具

PHM-Vibench
  ├── task dataset
  ├── train/val/test split
  ├── sampler / DataLoader
  ├── model / trainer
  └── benchmark protocol
```

独立包只负责“数据访问”。运行时主线是 IoTDB，Agent/CLI/MCP 查询不再依赖本地 `metadata.xlsx` 或 HDF5 cache；旧文件链路只用于迁移导入。

## 安装

开发安装：

```bash
pip install -e .
pip install -e '.[yaml,agent]'
```

只有需要把旧 `metadata.xlsx/CSV + HDF5` 导入 IoTDB 时，才安装 legacy extra：

```bash
pip install -e '.[legacy]'
```

## 启动或连接 IoTDB

本仓库提供本地测试容器：

```bash
cd docker/iotdb
docker compose up -d
phm-data-iotdb check
```

默认连接参数：

```yaml
backend: iotdb
default_max_points: 4096
iotdb:
  host: 127.0.0.1
  port: 6667
  user: root
  password: root
  root: root.vibench
```

也可以用环境变量覆盖：`IOTDB_HOST`、`IOTDB_PORT`、`IOTDB_USER`、`IOTDB_PASSWORD`、`IOTDB_ROOT`。

## 查询数据

```bash
phm-data --config examples/phm-data.iotdb.yaml summary
phm-data --config examples/phm-data.iotdb.yaml datasets
phm-data --config examples/phm-data.iotdb.yaml search --task fault --limit 10
phm-data --config examples/phm-data.iotdb.yaml metadata 1
phm-data --config examples/phm-data.iotdb.yaml window 1 \
  --start 0 --end 12000 --channels 0,1 --max-points 1024
```

所有输出都是 JSON。`get_signal_window` / `window` 默认限流；若返回 `step > 1`，它是给 Agent 阅读的均匀预览，不是完整训练 tensor。

Python 用法：

```python
from phm_data_factory import AgentDataTools, RepositoryConfig, build_repository

config = RepositoryConfig.from_mapping(
    {"backend": "iotdb", "iotdb": {"root": "root.vibench"}}
)

with build_repository(config) as repo:
    tools = AgentDataTools(repo)
    print(tools.repository_summary())
```

## 本地 Agent / MCP

配置文件建议使用 `examples/phm-data.iotdb.yaml`：

```bash
phm-data-mcp --config /absolute/path/phm-data.iotdb.yaml
```

Agent 工具：

```text
repository_summary
list_datasets
search_samples
get_sample_metadata
get_signal_statistics
get_signal_window
validate_sample
```

## 迁移旧 metadata + HDF5

旧本地文件只作为一次性导入源：

```bash
phm-data-iotdb import --config config/phm-data.yaml --report import-report.json
# --metadata/--signals 可选：未传时从 config 的 metadata_path/signal_path 读
# （config/phm-data.yaml 从 config/phm-data.sample.yaml 拷贝并填路径）
# --sample-id <id> 试导单样本；--chunk-size 控制批次
```

`--signals` 可指向单个 `cache.h5`、单个数据集 HDF5，或包含 `<Name>.h5` 的目录。HDF5 key 支持 `1`、`Id_1`、`sample_1`。

导入后的 IoTDB 路径：

```text
root.vibench.<dataset>.sample_<Id>.signal.ch_<channel>
root.vibench.<dataset>.sample_<Id>.meta.<field>
```

迁移完成后，日常查询、MCP 和 Agent 只需要 IoTDB。

## 接入 PHMFactory

PHMFactory v0.3.0 不包含该可选 backend。v0.3.1 由 PHMFactory 仓库中的 bounded adapter PR 接入组织仓库与 immutable gitlink；不要复制旧 overlay，也不要把 submodule checkout 注入 `sys.path`。具体边界见 [PHMBENCH_INTEGRATION.md](PHMBENCH_INTEGRATION.md)。

## 当前验证范围

- 单元测试覆盖 legacy metadata/HDF5、IoTDB mock、CLI/config 和导入边界；
- Wheel 构建命令：`python -m pip wheel --no-deps --no-build-isolation .`；
- IoTDB 2.0.8 已完成 12 样本小批量验收，并于 2026-08-01 用全新实例重跑合成样本导入、live pytest 和 AgentDataTools 受限窗口链路；约 250GB 全量导入与性能仍未验证。
