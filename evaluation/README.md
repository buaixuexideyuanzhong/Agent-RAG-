# 活动策划系统质量评估

衡量整体策划系统质量：对一组测试需求跑真实策划，自动计算客观指标，并对方案质量打分。

## 运行

在项目根目录，用 `huodongcehua` 环境的 python：

```bash
# 跑全部 12 条用例，manual 评分（质量维度输出评分表供人工填）
python -m evaluation.run_evaluation

# 只跑前 N 条（快速验证）
python -m evaluation.run_evaluation --limit 3

# 质量维度用 GLM 自动打分（每条方案额外消耗一次 LLM 调用）
python -m evaluation.run_evaluation --judge llm
```

结果输出到 `evaluation/results/<时间戳>/`：每个用例一个 JSON、`summary.json`（汇总指标）、`report.md`（可读报告）。

> ⚠️ **重要**：请先 `docker compose up -d` 启动 MySQL/Milvus/Redis 再评测。否则系统会全部降级为纯 LLM 生成——约束类/结构类指标仍可测，但"工具真实命中率"会失真（不代表真实水平）。

## 指标定义

### 客观指标（自动计算）

| 指标 | 定义 | 说明 |
|---|---|---|
| **需求提取准确率** | 提取结果字段与真值逐字段比对正确数 / 检查字段数 | 数值 ±20% 容差，文本包含匹配 |
| **方案约束召回率** | 方案正确覆盖的约束数 / 用户提出的约束总数 | 漏掉或做错都会扣分 |
| **方案约束准确率** | 方案正确覆盖的约束数 / 方案提到的约束数 | 只扣"提到但做错"（如人数写错） |
| **工具真实命中率** | 场地/商家/流程三节点未降级且未失败的比例 | 由 errors 中的"降级/失败"标记判定 |
| **结构完整性** | 方案覆盖概述/流程/场地/商家/预算/任务/风险板块比例 | 关键词启发式检查 |

> 约束真值来自 `test_cases.json` 的 `expected_constraints`。数值容差 ±20%，文本用包含匹配——这是**启发式**指标，用于趋势对比（调参前后），具体数值仅供参考。

### 质量维度分（5 分制）

`--judge manual`（默认）：`report.md` 输出每条方案的评分表，人工按以下维度打分后自行统计。

`--judge llm`：用 GLM 按 rubric 自动打分（完整性 / 可执行性 / 预算合规 / 逻辑一致 / 信息真实）。

## 数据文件

- `test_cases.json` — 12 条测试需求 + 约束真值（覆盖信息完整/缺失、特殊需求、极端规模、预算敏感、强时间约束、主题明确等边界）
- `seed_cases.json` — 20 条种子案例，用于扩充知识库（导入命令见下）

## 初始化知识库

```bash
# 起基础设施后，先导入种子案例（让"流程参考"节点有 RAG 可命中）
python -m backend.cli.main import evaluation/seed_cases.json
```

## 结果解读与调优

| 现象 | 指向 | 对策 |
|---|---|---|
| 约束召回率低 | 需求提取漏字段或整合遗漏 | 调整 `requirement_extractor` 的提取 prompt |
| 约束准确率低 | 提取或整合过度泛化（人数/预算写错） | 检查 `integrator` 对约束的遵守 |
| 结构完整性低 | 输出板块缺失 | 检查 `PLANNER_SYSTEM_PROMPT` 的输出格式约束 |
| 工具命中率低 | 工具 key 缺失 / 超时 / 降级 | 排查 `.env` 的 AMAP/BAIDU/BOCHA key |
| 预算合规分低 | 整合节点预算控制弱 | 强化 `PLANNER_SYSTEM_PROMPT` 的预算硬约束 |
