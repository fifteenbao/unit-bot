# unit-bot

> **扫地机器人 PLANS 价值设计平台** — 12 个独立子 agent，串成一条从竞品研究到体系建设的极致降本工作流。

This repo is also configured for Codex, Claude Code, OpenClaw, and similar coding agents. See [AGENTS.md](AGENTS.md) for the shared operating guide.

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

### 首次使用：本地数据准备

仓库 `.gitignore` 已排除 `data/lib/` `data/bom/` `data/teardowns/` 等私有数据目录，clone 下来后这些目录是空的。最简上手路径：

```bash
mkdir -p data/lib data/bom data/products data/plans data/teardowns

# 1. 把你的产品 BOM CSV (金蝶/SAP 导出) 放进 data/bom/
cp /your/path/some_model.csv  data/bom/some_model.csv

# 2. 跑 cost_mfg_bom.py 即可（即使 lib 三库为空也会用 default 兜底价）
python scripts/cost_mfg_bom.py data/bom/some_model.csv --msrp 2999
```

进一步逐步沉淀数据：
- **materials.csv / suppliers.csv**：手工维护或让 `/dfm` agent 自动推理回写
- **processes.csv / molds.csv / tooling.csv**：用 `/dfm` 跑一次会建议种子条目；模号请用脱敏编号（如 `MOLD-INJ-S-001`）
- **components_lib.csv**：跑 `scripts/fetch_fcc.py ocr` + `scripts/build_components.py` 自动入库

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
python scripts/cost_mfg_bom.py data/bom/xxx.csv --msrp 2999        # 制造 BOM (金蝶/SAP 格式) + Should Cost 对比
python scripts/build_components.py                                 # FCC OCR 结果入标准件库
```

#### `cost_mfg_bom.py` 输出示例

跑完会同时打出三段：
1. **7 桶汇总** —— 桶金额 / BOM% / 件数 / 与理论区间对比
2. **各桶 Top 件明细** —— 排序后单件成本，标注查价来源
3. **Should Cost vs 估算价对比表** —— 递归到 L3+ 子件，按 `process_id` + `mold_id` 命中三库 + 工艺级默认值后聚合：

```
Should Cost vs 估算价  (递归 L3+ 子件 → process/mold/tooling)
桶                       估算价   Should   gap%     覆盖     子件命中
算力与电子               190.3     14.5  1213%    67%     11/243 ⚠虚高
感知系统                 202.4     34.7   484%    62%     41/27  ⚠虚高
动力与驱动               140.4     37.7   273%    67%     66/81  ⚠虚高
清洁功能                 226.7     97.0   134%   100%    185/153 ⚠虚高
基站系统                 343.4     97.7   251%    83%    171/168 ⚠虚高
能源系统                  71.0       —      —     0%        —  (成品模块/未覆盖)
整机结构CMF              202.5     98.2   106%    82%    171/64  ⚠虚高
合计 (仅覆盖件)         1305.7    379.7   244% 133/166件  L3+子件命中 645/736
```

- `估算价`：来自 `components_lib.csv`，近似整机厂入库 BOM 价。
- `Should Cost`：材料 + 加工 + 模具摊销 + 工具折旧 + 合理利润，独立于 `components_lib.csv` 查价。
- `gap%`：估算价相对 Should Cost 的溢价比例。

  ```text
  gap% = (估算价 - Should Cost) / Should Cost × 100%
  ```

  例如 `gap=106%` 表示估算价约为 Should Cost 的 2.06 倍。
- `覆盖` / `子件命中`：表示本桶有多少子件能命中工艺、模具、工具数据；覆盖越高，Should Cost 越可信。

#### 解读：哪个桶最值得做 DFM 谈判？

结构件、注塑件、五金件等工艺覆盖完整的桶，更适合用 Should Cost 做谈判锚点。芯片、光学、电池等成品模块不适合直接套材料+加工模型，应改用元器件 BOM 或市场报价对标。

---

## 数据架构

系统维护 9 个数据库，分工明确（CSV/JSON 都在 `data/` 下，**`data/lib/` 和 `data/bom/` 已被 .gitignore，本地数据不会进 git**）：

| # | 数据库 | 文件 | 回答的问题 | 状态 |
|---|-------|------|-----------|:---:|
| ① | 产品规格库 | `data/products/products_db.json` | 这台机器**是什么** | ✅ |
| ② | 拆机档案 | `data/teardowns/{slug}_*.csv` + `fcc/{slug}/` | 这台机器**用了什么件** | ✅ |
| ③ | 标准件库 | `data/lib/components_lib.csv` | 这类件**值多少钱** | ✅ |
| ④ | 材料库 | `data/lib/materials.csv` | 原材料**怎么定价**（22 牌号种子） | ✅ |
| ⑤ | 供应商库 | `data/lib/suppliers.csv` | **谁在供货**、应该成本是多少 | ✅ |
| ⑥ | **工艺库** | `data/lib/processes.csv` | 这个件**怎么做出来**、工时多少（22 工艺基线） | ✅ |
| ⑦ | **模具库** | `data/lib/molds.csv` | 模具**摊销多少**、寿命多少（25 模号种子） | ✅ |
| ⑧ | **加工工具库** | `data/lib/tooling.csv` | 用什么**夹具/刀具**、单件折旧多少（21 治具种子） | ✅ |
| ⑨ | PLANS 研究库 | `data/plans/plans_db.json` + `{slug}/*.md` | 我们做过哪些**降本研究** | ✅ |

### Should Cost 五要素建模（⑥⑦⑧ 是 `/dfm` 的核心输入）

```
应该成本 = 材料④ + 加工⑥ + 模具摊销⑦ + 工具折旧⑧ + 合理利润
              ↑       ↑          ↑           ↑
       query_materials  query_processes  query_molds  query_tooling
```

每要素都有专用 tool，子 agent 可直接调用：

| Tool | 库 | 关键字段 |
|------|----|------|
| `query_materials` | materials.csv | name / grade / density / price_min/max / bom_bucket |
| `query_processes` | processes.csv | process_id / cycle_sec / hourly_rate_cny / scrap_rate_pct |
| `query_molds` | molds.csv | mold_id / related_parts / cavity_count / unit_amortization_cny |
| `query_tooling` | tooling.csv | tooling_id / bound_process / unit_depreciation_cny |
| `query_suppliers` | suppliers.csv | category / tier / region |

> 💡 **数据敏感性**：`molds.csv` 的 `mold_id` 字段建议使用**内部脱敏编号**（如 `MOLD-INJ-S-001` `MOLD-INJ-L-007`）而非厂商真实模号，避免敏感数据泄露。整个 `data/lib/` 目录已被 `.gitignore`，不会进 git。

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
├── agent.py                   # 主 orchestrator（含 15 个 plans_* + 5 个 query_*）
├── 价值设计流程PLANS.md         # PLANS 方法论原文（事实来源）
│
├── agents/      # 12 个 PLANS 子 agent，每个一目录 → agents/README.md
│   ├── p_research / p_teardown / p_issues       # P 阶段
│   ├── l_dfa / l_dfm                            # L 阶段 (DFM Should Cost 五要素已接齐)
│   ├── a_function / a_trim                      # A 阶段
│   ├── n_fos / n_patent / n_trend               # N 阶段
│   └── s_platform / s_costsystem                # S 阶段
├── core/        # 7 桶框架 / 标准件库 / 工艺-模具-工具三库加载器 (process_lib.py)
├── scripts/     # CLI 等价脚本（批量场景用）
├── docs/        # 架构设计稿
└── data/        # 9 个数据库的物理存储 (data/lib/ 整体 .gitignore)
```

### 信息闭环（数据流）

```
P /teardown  ── bom_level + material + process + mold_id + supply_mode
P /issues    ── key_part_flag + frequency_pct + evidence_url
                   ↓
L /dfa       ── 装配工时强制查 query_processes（process_id + saved_formula）
L /dfm       ── Should Cost 五要素全部查库（4 库 query_* + 12% 利润）
                   ↓
A /function  ── value_evidence / cost_evidence 强制引用上游
A /trim      ── 三级裁剪 + 39×39 矛盾矩阵 + 架构瓶颈
                   ↓
N /fos       ── evidence_from_trim + user_pain_ref + cost_evidence
N /patent    ── patent_url + jurisdiction + evidence_from_fos
N /trend     ── industry_position_evidence (出货量/均价/性能刷新)
                   ↓
S /platform  ── shared_parts_rate 公式化 + mold_reuse_count + roi_should_cost_delta
S /costsystem ─ 5 维体系（组织/设施/能力/数据/流程）
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
