# IoTDB PHM 数据读取完整指南

## 执行摘要

**当前状态：代码已就绪，运行时环境需要配置**

本仓库已经完整实现了 IoTDB 集成，可以通过 Apache IoTDB 读取 PHM 数据。本文档提供完整的启动和使用步骤。

---

## 一、当前状态概览

### 代码层面：已就绪 ✓
- `apache-iotdb>=2.0.8,<3` 依赖已配置
- CLI 工具可用：`phm-data`, `phm-data-mcp`, `phm-data-iotdb`
- 完整的 IoTDB 集成实现

### 运行层面：需要配置 ✗
- IoTDB 服务需要启动
- PHM 数据需要导入
- Docker 环境需要配置

### 四阶段验收状态

| 状态 | 判定命令 | 成功标准 |
| --- | --- | --- |
| `code-ready` | `pytest -q` | 单元测试通过，IoTDB mock 导入/读取逻辑可用 |
| `iotdb-connected` | `phm-data-iotdb check` | 能连接到 `host:port` |
| `data-imported` | `phm-data-iotdb import ... --report import-report.json` | `failed_count == 0` 或失败样本有明确原因 |
| `phm-readable` | `phm-data summary` + `phm-data window <sample_id>` | summary 有样本数，window 返回非空 `values` |

---

## 二、详细启动和使用指南

### 2.1 前置条件检查

#### 步骤 1: 验证 Python 环境
```bash
# 确认在项目目录中
cd /mnt/e/2_work/LQQL_OS/lqql_06_工作与项目/03_论文流水线/P01-phm-data-factory

# 检查虚拟环境
ls -la .venv/

# 激活虚拟环境（如需要）
source .venv/bin/activate

# 验证 CLI 工具可用
phm-data --help
phm-data-iotdb --help
```

#### 步骤 2: 配置 Docker（WSL2 环境）

**选项 A: 启用 Windows Docker Desktop WSL2 集成**
1. 打开 Windows Docker Desktop
2. 进入 Settings → Resources → WSL Integration
3. 启用 "Enable integration with my default WSL distro"
4. 确保 "Enable support for Linux distributions" 已勾选
5. 点击 "Apply & Restart"
6. 在 WSL2 中验证：
   ```bash
   docker --version
   docker compose version
   ```

**选项 B: 使用 Docker Desktop 直接运行**
在 Windows PowerShell 或 CMD 中：
```powershell
cd E:\2_work\LQQL_OS\lqql_06_工作与项目\03_论文流水线\P01-phm-data-factory\docker\iotdb
docker compose up -d
```

---

### 2.2 启动 IoTDB 服务

#### 步骤 3: 启动容器
```bash
cd docker/iotdb
docker compose up -d

# 查看容器状态
docker compose ps

# 查看日志（确认启动成功）
docker compose logs -f
```

预期输出应包含类似 "IoTDB is running" 的消息。

#### 步骤 4: 验证连接
```bash
# 在项目根目录执行
phm-data-iotdb check
```

如果成功，应显示 JSON：

```json
{
  "connected": true,
  "host": "127.0.0.1",
  "port": 6667
}
```

---

### 2.3 导入 PHM 数据

#### 步骤 5: 准备数据
确保你有以下数据：
- `metadata.xlsx` 或 `metadata.csv` - 样本元数据
- 信号数据目录 - 包含 HDF5 或 NPZ 文件

#### 步骤 6: 执行导入
```bash
phm-data-iotdb import \
  --metadata /path/to/metadata.xlsx \
  --signals /path/to/signals/directory \
  --root root.vibench \
  --chunk-size 10000 \
  --report import-report.json
```

参数说明：
- `--metadata`: 元数据文件路径
- `--signals`: 信号数据目录
- `--root`: IoTDB 根路径（默认 root.vibench）
- `--chunk-size`: 批量写入大小
- `--report`: 生成导入报告，报告内包含 `data_manifest`

#### 步骤 7: 验证导入结果
```bash
phm-data --root root.vibench summary
phm-data --root root.vibench datasets
phm-data --root root.vibench metadata 1
phm-data --root root.vibench window 1 --start 0 --end 1024 --max-points 128
```

导入报告中的 `data_manifest` 可作为论文证据链的一部分，记录：

```text
schema_version
root
metadata_query
signal_path_pattern
metadata_fields
metadata/source hashes
imported_sample_ids
failed_sample_ids
```

若要把真实 IoTDB 读数纳入测试，可在已导入数据后运行：

```bash
PHM_IOTDB_LIVE=1 pytest -q tests/test_iotdb_live.py
```

---

### 2.4 使用数据访问接口

#### CLI 使用示例
```bash
# 查看仓库概览
phm-data --root root.vibench summary

# 列出所有数据集
phm-data --root root.vibench datasets

# 搜索样本
phm-data --root root.vibench search --filter name=CWRU --limit 5

# 获取样本元数据
phm-data --root root.vibench metadata 1

# 获取信号窗口
phm-data --root root.vibench window 1 \
  --channels 0,1,2 --start 0 --end 1000 --max-points 256

# 信号统计
phm-data --root root.vibench stats 1 --channels 0,1,2
```

#### Python API 使用示例
```python
from phm_data_factory import AgentDataTools, RepositoryConfig, build_repository

# 配置 IoTDB 连接
config = RepositoryConfig.from_mapping({
    "backend": "iotdb",
    "iotdb": {
        "host": "127.0.0.1",
        "port": 6667,
        "user": "root",
        "password": "root",
        "root": "root.vibench"
    }
})

# 构建仓库
with build_repository(config) as repo:
    tools = AgentDataTools(repo)

    # 获取概览
    summary = tools.repository_summary()
    print(summary)

    # 列出数据集
    datasets = tools.list_datasets()
    print(datasets)

    # 搜索样本
    samples = tools.search_samples(name="CWRU", limit=10)
    print(samples)

    # 获取信号数据
    window = tools.get_signal_window(
        sample_id="1",
        channels=[0, 1, 2],
        start=0,
        end=1000,
        max_points=256,
    )
    print(window)
```

#### MCP Agent 工具使用
启动 MCP 服务器：
```bash
phm-data-mcp --config examples/phm-data.iotdb.yaml
```

可用工具：
- `repository_summary` - 仓库概览
- `list_datasets` - 数据集列表
- `search_samples` - 样本搜索
- `get_sample_metadata` - 获取样本元数据
- `get_signal_statistics` - 信号统计
- `get_signal_window` - 信号窗口获取
- `validate_sample` - 样本验证

---

### 2.5 常见问题排查

#### 问题 1: Docker 连接失败
```bash
# 检查 Docker 服务状态
docker ps

# 检查端口占用
netstat -an | grep 6667

# 重启 Docker Desktop
```

#### 问题 2: IoTDB 连接被拒绝
```bash
# 检查容器日志
docker compose logs iotdb

# 重启容器
docker compose restart
```

#### 问题 3: 数据导入失败
```bash
# 检查数据文件权限
ls -la /path/to/signals/

# 使用 --chunk-size 参数减少批次大小
phm-data-iotdb import --chunk-size 5000 ...
```

---

### 2.6 停止和清理

#### 停止 IoTDB 服务
```bash
cd docker/iotdb
docker compose down
```

#### 清理数据（谨慎使用）
```bash
# 删除容器和数据卷
docker compose down -v

# 删除数据目录
rm -rf data/ logs/
```

---

## 三、快速参考

### 环境变量配置
```bash
export IOTDB_HOST=127.0.0.1
export IOTDB_PORT=6667
export IOTDB_USER=root
export IOTDB_PASSWORD=root
export IOTDB_ROOT=root.vibench
```

### 配置文件位置
- IoTDB 配置: `docker/iotdb/docker-compose.yml`
- 示例配置: `examples/phm-data.iotdb.yaml`
- 快速开始: `docs/QUICKSTART_ZH.md`

### 关键命令
```bash
phm-data              # 数据查询 CLI
phm-data-mcp          # MCP 服务器
phm-data-iotdb        # IoTDB 管理工具
```

### IoTDB 路径结构
```
root.vibench.<dataset>.sample_<Id>.signal.ch_<channel>  # 信号数据
root.vibench.<dataset>.sample_<Id>.meta.<field>         # 元数据
```

---

## 四、相关文档
- [QUICKSTART_ZH.md](QUICKSTART_ZH.md) - 快速开始指南
- [ARCHITECTURE.md](ARCHITECTURE.md) - 架构说明
- [GOAL.md](GOAL.md) - 项目目标
