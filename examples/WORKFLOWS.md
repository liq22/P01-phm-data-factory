# examples workflows

本页给出可直接照抄的运行流程。真实数据路径写到本地
`config/phm-data.yaml`，不要提交机器私有路径。

## 1. Local smoke：先确认 metadata + HDF5 可读

适用场景：迁移到 IoTDB 前，先确认本机 metadata 和信号文件能被
`phm-data-factory` 正常读取。

```bash
cp config/phm-data.sample.yaml config/phm-data.yaml
# 编辑 config/phm-data.yaml:
#   backend: local
#   metadata_path: /abs/path/to/metadata.xlsx
#   signal_path: /abs/path/to/cache.h5 或 /abs/path/to/signals_dir

phm-data --config config/phm-data.yaml summary
phm-data --config config/phm-data.yaml datasets
phm-data --config config/phm-data.yaml metadata 1
phm-data --config config/phm-data.yaml window 1 --start 0 --end 1024 --channels 0,1 --max-points 128
```

期望：`summary` 有样本数，`window` 返回非空 `values`。

## 2. Import to IoTDB：一次性导入和校验

适用场景：本地数据已可读，需要把样本写入 IoTDB。

```bash
phm-data-iotdb check --config config/phm-data.yaml

phm-data-iotdb import \
  --config config/phm-data.yaml \
  --report import-report.json

python scripts/verify_metadata.py --config config/phm-data.yaml
```

小批量冒烟时先加 `--sample-id 1`。全量导入失败时优先看
`import-report.json` 的 `failed` 字段，不要直接重跑覆盖问题。

## 3. Pure IoTDB runtime：日常查询和训练侧读接口

导入完成后，把本地配置切到纯 IoTDB：

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

纯 IoTDB 模式不写 `metadata_path` / `signal_path`；catalog 从 IoTDB 的
`.meta` 设备加载。

```bash
phm-data --config config/phm-data.yaml summary
phm-data --config config/phm-data.yaml datasets
phm-data --config config/phm-data.yaml search --task fault --limit 10
phm-data --config config/phm-data.yaml metadata 1
phm-data --config config/phm-data.yaml window 1 --start 0 --end 4096 --channels 0,1 --max-points 512
```

Python 侧使用 v0.2 稳定合同：

```python
from phm_data_factory import connect

with connect("config/phm-data.yaml") as repo:
    rows = repo.search_samples({"name": "RM_001_CWRU"}, limit=5)
    sid = rows[0]["sample_id"]
    meta = repo.get_sample_metadata(sid)
    x = repo.read_signal(sid, start=0, end=4096, channels=[0, 1])
```

可运行示例：

```bash
PYTHONPATH=src python examples/iotdb_backend_quickstart.py
```

该示例依赖本机 `config/phm-data.yaml` 和已导入的 live IoTDB。

## 4. MCP / Agent：只读工具面

适用场景：给 Claude Desktop、Cursor 或其他 MCP client 暴露只读数据工具。

```bash
phm-data-mcp --config /absolute/path/to/config/phm-data.yaml
```

客户端配置参考 `examples/mcp-client.json`。Agent/MCP 工具面保持只读：
查询 summary、dataset、metadata、window、statistics 和 validation；不暴露写入工具。

## 5. Notebook：受控演示

`examples/iotdb_python_read_write.ipynb` 展示 factory API 与底层
`apache-iotdb` Session 的受控读写。Notebook 默认不写入 IoTDB；确认目标
`root` 后，再显式打开写入开关。
