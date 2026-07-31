# Session Handoff: 新会话上下文整理

**Date:** 2026-07-21 11:40:31 +0800
**Project:** P01-phm-data-factory

## Current State

- Task: 整理当前会话上下文，供新会话继续使用。
- Phase: 尚未开始具体开发、诊断、数据分析或实验任务。
- Progress: 已确认项目规则、仓库状态和交接位置。
- Git: 当前分支为 `feat/iotdb-v02-store-contract`，开始整理前与 `origin/feat/iotdb-v02-store-contract` 对齐，工作树干净。

## What Was Done

- 读取并确认根目录 `AGENTS.md`。
- 记录本次会话中用户提供的全局工作约定和项目级 Agent 数据访问约束。
- 未读取或修改原始数据，未运行实验，未改动产品代码。

## Decisions and Rationale

- 后续 Agent 数据访问必须使用 `AgentDataTools` 或 MCP；不得向 Agent 暴露任意 Pandas 查询字符串、不受限的 IoTDB SQL 或原始 HDF5 句柄。
- 数据探索顺序固定为：summary → structured search → metadata → statistics → bounded window → validation。
- 不把 IoTDB import 暴露为 Agent 工具，因为它会改变存储状态。
- 原始数据默认不可变；派生数据、检查点、图表和报告应写到独立且可追踪的位置。
- 接受指标前必须检查数据泄漏路径，包括训练/验证/测试边界、主体或机器分组、时间顺序和预处理拟合范围。
- 未经明确授权，不安装依赖、不下载大型资源、不改变远端状态，也不提交、推送、发布或部署。

## Changed Paths

- `docs/handoffs/2026-07-21-1140-session-context.md` — 新增本交接记录。

## Verification

- 已执行 `git status --short --branch`：创建交接前工作树无改动。
- 已确认仓库根目录和当前分支。
- 未运行测试、静态检查或实验；本次会话没有实现变更需要验证。

## Blockers and Open Questions

- 当前无技术阻塞。
- 新会话尚需用户给出具体任务目标、完成标准和必要输入。

## Next Steps

1. [ ] 新会话先阅读根目录 `AGENTS.md` 和本交接文件。
2. [ ] 执行 `git status --short --branch`，确认是否出现新的用户改动。
3. [ ] 根据用户的新任务，先探索可发现的仓库事实，再确定最小且可验证的实施方案。
4. [ ] 若涉及 Agent 数据查询，严格遵循项目规定的数据访问接口与六阶段顺序。

## Files to Review

- `AGENTS.md`
- `docs/handoffs/2026-07-21-1140-session-context.md`
