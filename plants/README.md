# PLANTS：通用 PLANS 价值工程项目

## 1. 这个项目是做什么的

PLANTS 是一个面向实体产品的价值工程工作台。它把产品研究、拆解分析、设计降本、功能裁剪、技术创新和成本体系建设串成一条可追溯流程。

它适合这样的工作：

- 研发团队想知道产品哪些零件、工序或功能成本过高；
- 成本工程师需要把报价拆成材料、加工、模具、工具和利润；
- 产品经理需要在不损害核心体验的情况下删减复杂度；
- 企业希望把一次性降本项目沉淀为平台化、标准化和 NPI 流程。

PLANTS 本身不提供某个行业的真实价格、供应商或产品结论。它提供通用的阶段方法、任务包、依赖检查、证据校验、确定性计算和报告归档。行业资料由项目团队提供，模型或人工智能体负责分析。

## 2. 在智能体中使用：一个完整案例

下面以“新开发一台机电泵，目标是降低单位成本 12%，同时保持流量、扬程和寿命指标”为例。ChatGPT、Codex、Claude Code、Claude Desktop、OpenClaw 或本地模型都可以作为执行智能体。

### 第一步：准备项目和资料

在 `pump-project/` 下创建 `project.json` 和资料文件：

```json
{
  "id": "pump-p01",
  "name": "P-01 泵价值工程",
  "industry": "机电产品",
  "product": "泵 P-01",
  "currency": "CNY",
  "annual_volume": 10000,
  "objectives": ["单位成本降低 12%", "保持流量、扬程和寿命"],
  "constraints": ["安全法规不变", "不得降低关键可靠性指标"],
  "metrics": [
    {"name": "流量", "unit": "L/min", "target": 30},
    {"name": "扬程", "unit": "m", "target": 12},
    {"name": "设计寿命", "unit": "h", "target": 10000}
  ],
  "cost_categories": ["电机", "液力部件", "控制", "结构", "装配测试"],
  "source_files": ["brief.md", "bom.csv"],
  "entities": []
}
```

资料可以是产品简报、BOM、测试记录、维修记录、供应商报价或竞品资料。PDF、图片和 Excel 先整理成带页码、行号或条目位置的文字，方便智能体引用。

### 第二步：生成一个阶段任务包

```bash
cd /Users/bao/Documents/git/unit-bot/plants
python3 agent.py --project /path/to/pump-project/project.json \
  prepare research > /tmp/pump-research-task.json
```

### 第三步：让智能体执行任务

把 `/tmp/pump-research-task.json` 上传或粘贴到 ChatGPT、Claude 或 Codex，并发送：

> 这是 PLANS 的 P·产品研究任务包。请只依据任务包和可核验资料完成本阶段。区分 fact、inference、assumption；未知值填 null；每个条目填写 evidence_ids；不要修改项目文件；最后只返回一个完整结果 JSON。

智能体应输出产品定位、客户痛点、关键指标和竞品基线。若缺少泵的测试数据，它应把栏目留空并在 `limitations` 中说明，而不是猜测。

### 第四步：导入并推进流程

把智能体返回的 JSON 保存为 `/tmp/pump-research-result.json`，再执行：

```bash
python3 agent.py --project /path/to/pump-project/project.json \
  accept research /tmp/pump-research-result.json
python3 agent.py --project /path/to/pump-project/project.json /plans status
```

接着依次执行 `/teardown`、`/issues`、`/dfa`、`/dfm`……或直接运行 `/plans`。系统会检查前置阶段是否已经完成；例如 `/dfa` 会等待 `/teardown` 和 `/issues` 的有效结果。

### 在不同应用中的选择

**ChatGPT 或 Codex**：适合让智能体直接访问工作区。若有终端权限，可以执行 `prepare`、读取资料并将结果写入临时 JSON；仍通过 `accept` 入库。

**Claude Code**：把 `plants/` 或你的项目目录作为工作目录，先读 `README.md`、`AGENTS.md` 和目标阶段的 `prompt.md`，再执行同样的命令。

**Claude Desktop**：若没有本地文件工具，使用“任务包文件上传 → 对话生成结果 → 下载结果 JSON → 命令行 `accept`”的方式。Claude Desktop 不会自动读取你的磁盘。

**OpenClaw 或自建 Agent**：通过运行器批量执行：

```bash
python3 agent.py --project /path/to/pump-project/project.json \
  --runner 'python3 /path/to/runner.py' /plans
```

运行器从 stdin 读取任务包 JSON，从 stdout 返回一个结果 JSON；模型调用、联网搜索和只读资料访问由运行器负责，PLANTS 负责校验和归档。

## 3. PLANS 项目方法论

PLANS 是从“看清现状”到“固化收益”的五阶段价值工程路径：

完整的方法论原文请阅读仓库中的 [PLANS 价值设计流程.md](../PLANS%20价值设计流程.md)。该文档是本项目阶段职责、方法和依赖关系的事实来源。

| 阶段 | 要回答的问题 | 主要工作 | 主要产出 |
|---|---|---|---|
| **P · 现状研究** | 产品现在是什么样？客户真正需要什么？ | 定位、需求、竞品、拆解、问题 | 事实基线、BOM 和问题清单 |
| **L · 精益设计** | 怎样用更少的零件、材料、工序实现同样功能？ | DFA、DFM、Should Cost | 装配/制造优化方案和成本模型 |
| **A · 先进裁剪** | 哪些功能、零件或载体可以删除、合并或替换？ | 功能价值分析、TRIZ 裁剪和矛盾分析 | 裁剪决策和架构瓶颈 |
| **N · 价值创新** | 有没有跨行业的新方式实现更高价值或更低成本？ | FOS、专利规避、趋势和四新设计 | 替代方案池和创新路线图 |
| **S · 体系建设** | 怎样让本次收益持续发生？ | 平台化、组织、数据、能力、NPI 门 | 成本体系和持续改善机制 |

顺序很重要：P 建立事实，L 消除直接浪费，A 检查结构性裁剪，N 寻找下一条技术路径，S 把经过验证的收益固化。跳过上游阶段会缺少证据，系统会显示 `blocked`。

三个原则贯穿所有阶段：

1. 先事实后判断：事实、推断和假设分开记录；
2. 先功能后成本：先确认客户价值，再决定删减什么；
3. 先验证后固化：方案必须有风险、验证计划和适用边界。

## 4. 命令和依赖

| 阶段 | 命令 | 必需前置 |
|---|---|---|
| P | `/research`、`/teardown`、`/issues` | 无 |
| L | `/dfa` | `/teardown`、`/issues` |
| L | `/dfm` | `/teardown` |
| A | `/function` | `/dfa`、`/dfm` |
| A | `/trim` | `/function` |
| N | `/fos` | `/trim` |
| N | `/patent` | `/fos` |
| N | `/trend` | 无 |
| S | `/platform`、`/costsystem` | `/trim`、`/fos` |

```bash
python3 agent.py --project project.json /plans
python3 agent.py --project project.json /plans status
python3 agent.py --project project.json /plans overview
```

## 5. 数据、结果和状态

默认输出在 `data/<project-id>/`：`stages.json` 保存结构化结果，`<stage>.md` 保存阶段报告，`overview.md` 保存总览。

结果必须保留任务包的 `packet_id`，包含 `summary`、阶段栏目、`evidence` 和 `limitations`；每个分析条目通过 `evidence_ids` 引用证据。资料、提示词、项目配置或上游结果变化后，旧结果会标记为 `stale`。

`core/calculations.py` 提供 `should_cost`、`assembly`、`roi` 和 `commonality` 计算合同。模型提交输入和来源，代码计算输出，避免把关键算术交给模型。

状态含义：`ready` 可执行，`blocked` 缺前置，`complete` 已通过结构校验，`stale` 需要重跑。`complete` 不是事实真实性或工程安全性的保证，仍需项目团队复核。

## 6. 开发和扩展

```bash
python3 -m unittest discover -s tests -v
```

阶段注册表在 `agents/registry.json`，通用提示词在各阶段 `prompt.md`，编排和存储在 `core/workflow.py`。行业专用的七桶成本、供应商库、FCC/OCR 和产品别名仍属于原 `unit-bot`，不会进入通用核心。

更多说明见 [架构边界](docs/architecture.md)、[阶段维护](agents/README.md) 和 [代理操作指南](AGENTS.md)。
