# examples

这里放可直接复用的配置和使用示例。真实路径建议写到本地 `config/phm-data.yaml`，不要提交到仓库。

| 文件 | 用途 |
|---|---|
| `phm-data.iotdb.yaml` | 纯 IoTDB 运行时配置示例，适合日常查询、MCP、Agent |
| `phm-data.local.yaml` | local metadata/HDF5 过渡配置示例，适合迁移前快速试读 |
| `iotdb_python_read_write.ipynb` | Python 读写 IoTDB notebook：factory API + 受控底层 Session 示例 |
| `mcp-client.json` | MCP client 配置示例 |
| `agent-manifest.json` | 只读 Agent 工具 manifest 示例 |

Notebook 默认不写入 IoTDB。确认目标 `root` 后，再把其中的 `RUN_IMPORT` 或 `RUN_LOW_LEVEL_DEMO` 改为 `True`。
