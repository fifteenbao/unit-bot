# unit-bot

> **扫地机器人 PLANS 价值设计平台** — 12 个独立子 agent，串成一条从竞品研究到体系建设的极致降本工作流。

```
P 现状研究  →  L 精益设计  →  A 先进裁剪  →  N 价值创新  →  S 体系建设
3 agent       2 agent (DFMA)  2 agent (TRIZ)  3 agent       2 agent
```

方法论原文：[价值设计流程PLANS.md](价值设计流程PLANS.md) · 架构设计：[docs/agents_architecture.md](docs/agents_architecture.md)

---

## 快速开始

```bash
git clone https://github.com/fifteenbao/unit-bot && cd unit-bot
pip install -r requirements.txt

# 配置 API Key
export DEEPSEEK_API_KEY=sk-xxx

python agent.py
```

或接入 OpenClaw（免配 key）：

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

---

## 命令一览

> 命令统一接受 `<品牌> <型号>` 格式（如 `石头 G30 Pro`、`追觅 X50 Ultra`）。

### PLANS 12 子 agent — 每个 agent 单一职责

| 阶段 | 命令 | Agent 角色 | 上游依赖 |
|------|------|-----------|---------|
| **P** 现状研究 | `/research <品牌> <型号>` | 产品研究员 | — |
| | `/teardown <品牌> <型号>` | 拆解分析师 | — |
| | `/issues <品牌> <型号>` | 问题诊断师 | — |
| **L** 精益设计 | `/dfa <品牌> <型号>` | DFA 优化师 | `/teardown` + `/issues` |
| | `/dfm <品牌> <型号>` | DFM 优化师（含 Should Cost） | `/teardown` |
| **A** 先进裁剪 | `/function <品牌> <型号>` | 功能建模师（TRIZ） | `/dfa` + `/dfm` |
| | `/trim <品牌> <型号>` | 裁剪策略师（TRIZ 矛盾） | `/function` |
| **N** 价值创新 | `/fos <品牌> <型号>` | 功能创新搜索师 | `/trim` |
| | `/patent <品牌> <型号>` | 专利规避师 ⚠️非法律意见 | `/fos` |
| | `/trend <品牌> <型号>` | 趋势分析师（S 曲线） | — |
| **S** 体系建设 | `/platform <品牌> <型号>` | 平台架构师 | `/trim` + `/fos` |
| | `/costsystem <品牌> <型号>` | 成本体系构建师 | `/trim` + `/fos` |

每个 agent 产出 `data/plans/{品牌型号}/{stage_key}.md` 报告。详细职责见 [agents/README.md](agents/README.md)。

### 编排器

```
/plans <品牌> <型号>              # 串行跑全 12 阶段（按依赖顺序）+ overview.md
/plans status <品牌> <型号>       # 查 12 阶段进度
/plans overview <品牌> <型号>     # 重新拼 overview.md（不重跑）
```

### 数据采集

底层数据采集工具（`generate_teardown_csv` / `vs_compare` / `find_parts` / `export_framework` 等）**已合并到 12 个子 agent 的工具白名单**——子 agent 在执行任务时自主调用，用户不需要手动跑。

**唯一需要用户手动跑的**：FCC 文档检索 + 芯片 OCR（涉及文件下载和视觉识别，不在 agent 工具集里）。

```bash
python scripts/fetch_fcc.py find "石头 G30S Pro"   # 查 FCC 文档链接
python scripts/fetch_fcc.py ocr  "石头 G30S Pro"   # 下载 PDF + OCR PCB 芯片
```

跑完后 `/teardown` 子 agent 会自动读取 `data/teardowns/fcc/{slug}/` 下的结果。

### 批量 / CI 场景的等价脚本

```bash
python scripts/import_products.py data/products/products.csv      # 批量导入产品规格
python scripts/gen_teardown.py "石头 G30S Pro" --msrp 5999         # 等价于 /teardown 内部产物
python scripts/cost_mfg_bom.py data/bom/xxx.csv --msrp 2999        # 制造 BOM (金蝶/SAP 格式)
python scripts/build_components.py                                 # FCC OCR 结果入标准件库
```

---

## 数据架构

系统维护 9 个数据库，分工明确：

| # | 数据库 | 文件 | 回答的问题 |
|---|-------|------|-----------|
| ① | 产品规格库 | `data/products/products_db.json` | 这台机器**是什么** |
| ② | 拆机档案 | `data/teardowns/{slug}_*.csv` + `fcc/{slug}/` | 这台机器**用了什么件** |
| ③ | 标准件库 | `data/lib/components_lib.csv` | 这类件**值多少钱** |
| ④ | 材料库 | `data/lib/materials.csv` | 原材料**怎么定价** |
| ⑤ | 供应商应该成本库 | `data/lib/suppliers.csv` | **谁在供货**、应该成本是多少 |
| ⑥ | 工艺库 | `data/lib/processes.csv` _(待建)_ | 这个件**怎么做出来**、工时多少 |
| ⑦ | 模具库 | `data/lib/molds.csv` _(待建)_ | 模具**摊销多少**、寿命多少 |
| ⑧ | 加工工具库 | `data/lib/tooling.csv` _(待建)_ | 用什么**夹具/刀具**、单件折旧多少 |
| ⑨ | PLANS 研究库 | `data/plans/plans_db.json` + `{slug}/*.md` | 我们做过哪些**降本研究** |

> ⑥/⑦/⑧ 三库是 `/dfm` 应该成本（Should Cost）建模的关键输入：
> **应该成本 = 材料（④）+ 加工工时×费率（⑥工艺）+ 模具摊销（⑦）+ 工具折旧（⑧）+ 合理利润**
> 三库 schema 设计中，先以 `/dfm` 子 agent 推理 + 行业基准估算填充，逐步沉淀。

### 标准件库入库规则

`components_lib.csv` 是查价权威表，仅接受高置信度来源：

| 来源标记 | 入库 | 说明 |
|---------|:---:|------|
| `confirmed` | ✓ | 人工 / 实物核实 |
| `teardown` | ✓ | 实物拆机 CSV |
| `fcc` | ✓ | FCC 文档 OCR 识别 |
| `inferred` | ✗ | 启发式推导 |
| `estimate` | ✗ | 行业基准估算 |
| `web` | ✗ | 网络调研 |

> 跑完 `python scripts/fetch_fcc.py ocr "<品牌> <型号>"` 后执行 `python scripts/build_components.py` 即可入库。

---

## 7 桶成本框架

`/teardown` 子 agent 产生的 BOM 按 7 桶组织（基准来自开源证券·科沃斯 T80S 拆解 2024）：

| # | 桶 | 基准占比 |
|:-:|----|:---:|
| 1 | 算力与电子 | ~13% |
| 2 | 感知系统 | ~16% |
| 3 | 动力与驱动 | ~11% |
| 4 | 清洁功能 | ~20% |
| 5 | 基站系统 | ~24% |
| 6 | 能源系统 | ~7% |
| 7 | 整机结构 CMF | ~13% |

整机 BOM 率：旗舰约 40~55%（硬件物料 / 零售价）。详细 4 级分解见 [SKILL.md](SKILL.md)。

---

## 项目结构

```
unit-bot/
├── agent.py                   # 主 orchestrator（46 工具，含 15 个 plans_*）
├── 价值设计流程PLANS.md         # PLANS 方法论原文（事实来源）
│
├── agents/      # 12 个 PLANS 子 agent，每个一目录 → agents/README.md
├── core/        # 7 桶框架 / 标准件库 / PLANS 数据库读写等核心模块
├── scripts/     # CLI 等价脚本（批量场景用）
├── docs/        # 架构设计稿
└── data/        # 6 个数据库的物理存储
```

完整文件树和各模块说明见 [agents/README.md](agents/README.md) 和 [docs/agents_architecture.md](docs/agents_architecture.md)。

---

## 进一步阅读

| 想了解 | 看哪里 |
|--------|--------|
| PLANS 方法论原文 | [价值设计流程PLANS.md](价值设计流程PLANS.md) |
| 12 子 agent 详细职责 + 文件约定 | [agents/README.md](agents/README.md) |
| 命令完整参数和使用细节 | [SKILL.md](SKILL.md) |
| 多 agent 编排架构设计 | [docs/agents_architecture.md](docs/agents_architecture.md) |
