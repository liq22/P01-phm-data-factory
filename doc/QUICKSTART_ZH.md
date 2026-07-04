# phm-data-factory 中文快速开始

## 目标边界

```text
phm-data-factory
  ├── metadata.xlsx / CSV 索引
  ├── HDF5 随机窗口读取
  ├── IoTDB 导入与读取
  ├── JSON CLI
  └── 只读 MCP Agent 工具

metadata 和 数据 在 E:\D01_vibench

PHM-Vibench
  ├── task dataset
  ├── train/val/test split
  ├── sampler / DataLoader
  ├── model / trainer
  └── benchmark protocol
```

独立包只负责“数据访问”，不把 PyTorch、训练器和 benchmark 策略带进 Agent 进程。

## 直接安装 Wheel

```bash
pip install phm_data_factory-0.1.0-py3-none-any.whl
pip install "mcp[cli]>=1.27,<2" "apache-iotdb>=2.0.8,<3" openpyxl PyYAML
```

开发安装：

```bash
pip install -e '.[excel,yaml,agent,iotdb]'
```

## 本地 metadata + HDF5

```bash
phm-data \
  --metadata /data/metadata.xlsx \
  --signals /data \
  summary

phm-data \
  --metadata /data/metadata.xlsx \
  --signals /data/cache.h5 \
  window 1 --start 0 --end 12000 --channels 0,1 --max-points 1024
```

`--signals` 可指向：

- 单个 `cache.h5`；
- 单个数据集 HDF5；
- 包含 `<Name>.h5` 的目录。

HDF5 key 支持 `1`、`Id_1`、`sample_1`。

## 本地 Agent / MCP

配置：

```yaml
backend: local
metadata_path: /data/metadata.xlsx
signal_path: /data
default_max_points: 4096
```

启动 stdio MCP server：

```bash
phm-data-mcp --config /absolute/path/phm-data.local.yaml
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

`get_signal_window` 默认限流；若返回 `step > 1`，它是给 Agent 阅读的均匀预览，不是完整训练 tensor。

## IoTDB

```bash
cd docker/iotdb
docker compose up -d  # 默认 apache/iotdb:2.0.8-standalone
phm-data-iotdb check
```

导入：

```bash
phm-data-iotdb import \
  --metadata /data/metadata.xlsx \
  --signals /data \
  --root root.vibench \
  --chunk-size 10000 \
  --report import-report.json
```

路径：

```text
root.vibench.<dataset>.sample_<Id>.signal.ch_<channel>
root.vibench.<dataset>.sample_<Id>.meta.<field>
```

## 接入 PHM-Vibench

把 overlay ZIP 解压到 PHM-Vibench 根目录并保留路径，然后：

```bash
pip install -e 'packages/phm-data-factory[excel,yaml,agent,iotdb]'
PYTHONPATH=. pytest -q packages/phm-data-factory/tests
pytest -q test/test_standalone_data_factory.py
```

现有训练入口不变；新增入口：

```python
from src.data_factory import build_agent_data_tools, build_data_repository

with build_agent_data_tools(args.data) as tools:
    print(tools.repository_summary())
```

## 当前验证范围

- 单元测试 11 项通过；
- Wheel 安装、CLI 和 MCP server 构造通过；
- IoTDB Python client 2.0.8 API 以及分块 aligned-tablet 写入通过 mock 测试；
- 当前环境未启动真实 IoTDB 容器，因此真实服务器 smoke test 需在有 Docker 的机器执行。

