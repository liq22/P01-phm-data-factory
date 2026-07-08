# 跨机全量导入执行手册

本手册给**在另一台电脑执行全量导入**的操作者。data-factory 代码与脚本已在源机 commit；本机 `git pull` 后按本手册执行。**数据目录变化时只改 `config/phm-data.yaml`**。

> 配套：[BENCHMARK_INTEGRATION.md](BENCHMARK_INTEGRATION.md)（接入+优化）、[IOTDB_GUIDE.md](IOTDB_GUIDE.md)（IoTDB 启动）、[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)（配置链）

---

## 0. 前置条件

- Python 3.10+（推荐 3.13）
- Java 11+（WSL2/Linux 直跑 IoTDB 时）；或 Docker（用 docker 跑 IoTDB 时）
- 数据：D01_vibench 全量（`metadata.xlsx` + `RM_*.h5`，~95GB）放在本机某路径

## 1. 拉代码 + 安装

```bash
git clone <repo-url> phm-data-factory   # 或在已有仓库 git pull
cd phm-data-factory
pip install -e '.[yaml,legacy]'         # YAML 配置 + HDF5 legacy 读
```

## 2. 启动 IoTDB（二选一）

**A. docker**（镜像 `apache/iotdb:2.0.8-standalone`）：
```bash
cd docker/iotdb && docker compose up -d
```
> WSL2 + Docker Desktop 非 mirrored 模式下，host python 经 docker-proxy 连接会报 `TSocket read 0 bytes`。解：开 mirrored networking，或用方案 B。

**B. WSL2/Linux 直跑二进制**（绕过 docker-proxy，推荐 WSL2）：
```bash
curl -fL -o iotdb.zip https://archive.apache.org/dist/iotdb/2.0.8/apache-iotdb-2.0.8-all-bin.zip
unzip -q iotdb.zip
export IOTDB_HOME=$(pwd)/apache-iotdb-2.0.8-all-bin
"$IOTDB_HOME/sbin/start-standalone.sh"   # 同机启 ConfigNode+DataNode，~50s ready
```

## 3. 配置 `config/phm-data.yaml`（**数据目录变化时改这里**）

```bash
cp config/phm-data.sample.yaml config/phm-data.yaml
# 编辑 config/phm-data.yaml：
#   metadata_path: <本机 metadata.xlsx 绝对路径>
#   signal_path:   <本机 D01_vibench 目录绝对路径>
#   iotdb: host/port/user/password/root（默认 127.0.0.1:6667/root/root/root.vibench）
```

> 路径必须本机有效（WSL2 `/mnt/x/...`、Linux `/abs/path`；**Windows 原生反斜杠 `E:\` 会解析失败**）。`config/phm-data.yaml` 已 gitignore（机器私有）。

## 4. 预检

```bash
phm-data-iotdb check                                # 期望 connected:true, exit 0
phm-data --config config/phm-data.yaml summary      # 数据可读 + datasets 列表
phm-data --config config/phm-data.yaml datasets     # 确认 19 个 dataset
```

## 5. 导入（按数据集过滤，剔除无文件）

```bash
python scripts/import_datasets.py --config config/phm-data.yaml \
    --all-except RM_005_Ottawa23,RM_006_THU,RM_007_MFPT \
    --skip-existing --continue-on-error \
    --report import-report.json
```

- `--all-except`：剔除 3 个**无 .h5 文件**的数据集（RM_005/006/007，95 样本，否则 `validate_sample` 失败）
- `--skip-existing`：断点续传（一次 SELECT 拿已导集合，跳过；重跑不重复写）
- `--continue-on-error`：失败样本（如 RM_004 B-tree 损坏）跳过继续，计入 `failed_sample_ids`
- `--report`：写 import-report.json（含 `data_manifest`，论文证据链）

**后台跑**（~95GB，串行 30-80h）：
```bash
nohup python scripts/import_datasets.py --config config/phm-data.yaml \
    --all-except RM_005_Ottawa23,RM_006_THU,RM_007_MFPT \
    --skip-existing --continue-on-error --report import-report.json \
    > import.log 2>&1 &
tail -f import.log
```

## 6. 验证 metadata 正确

```bash
python scripts/verify_metadata.py --config config/phm-data.yaml --report verify-report.json
```

**通过标准**：
- `only_in_source: 0`（已导数据集无遗漏；被 `--all-except` 剔除的不算）
- `field_diffs: 0`（15 SCHEMA 字段值一致，容忍 `_txt`/`as_bool` 类型转换 + 源空⇔IoTDB 无点）
- `missing_columns_in_iotdb: []`（SCHEMA 15 字段全在）

> `description` / `sample_type` / `label_description` / `rul_label_description` / `domain_description` 这 5 个**不在 SCHEMA**（设计性不导），不参与验证。

## 7. 数据障碍（已知）

| 数据集 | 问题 | 处理 |
|---|---|---|
| RM_005_Ottawa23 / RM_006_THU / RM_007_MFPT | metadata 有 95 样本，磁盘无 .h5 | `--all-except` 剔除 |
| RM_004_IMS | B-tree 损坏（7.6GB，h5py 无法遍历） | `--continue-on-error` 跳过（计入 failed） |
| RM_101_THU_GEARBOX | 磁盘有（5.9GB, 240 样本），metadata 无 | 不导（import 按 metadata 跑）；如需导先补 metadata 行 |

## 8. 断点续传

导入中断后，直接重跑同命令（`--skip-existing` 自动跳过已导；schema 幂等，数据 last-write-wins 覆盖但耗时相同）：
```bash
python scripts/import_datasets.py --config config/phm-data.yaml \
    --all-except RM_005_Ottawa23,RM_006_THU,RM_007_MFPT \
    --skip-existing --continue-on-error --report import-report.json
```

## 9. 切到 IoTDB 后端（导入完成后）

编辑 `config/phm-data.yaml`：`backend: iotdb`（删 `metadata_path`/`signal_path` 走纯 IoTDB）。

```bash
phm-data --config config/phm-data.yaml summary    # 纯 IoTDB 查询
```
