# PLANS 多 Agent 架构设计稿（12-Agent 版）

> 目标：按 [价值设计流程 PLANS](../价值设计流程PLANS.md) 把降本工作流拆成 **12 个边界清晰的子 agent**，每个 agent 单一职责、上下游依赖明确。
> 主 agent 是 orchestrator，只调度，不亲自做任何 PLANS 阶段的调研。

---

## 1. 总体结构

```
┌─────────────────────────────────────────────────────────┐
│  主 agent (orchestrator)  agent.py                       │
│  - 解析用户命令 → 路由到对应子 agent                       │
│  - 串行编排 /plans <product> （按依赖顺序）                │
│  - 汇总各阶段产出，写入 plans_db.json + .md                │
└─────┬───────────────────────────────────────────────────┘
      │ tool call: plans_research / plans_teardown / ...
      ▼
┌─────────────────────────────────────────────────────────┐
│ 12 子 agent（每个独立 prompt + tools 白名单 + JSON schema） │
│                                                          │
│ P (3): research / teardown / issues                      │
│ L (2): dfa / dfm                                         │
│ A (2): function / trim                                   │
│ N (3): fos / patent / trend                              │
│ S (2): platform / costsystem                             │
└─────────────────────────────────────────────────────────┘
```

每个子 agent 独立一次 `client.messages.create` 循环，运行结束后返回结构化 JSON。主 agent 接收后：
1. 把 JSON 写入 `data/plans/plans_db.json` 的 `[product_key].stages.{stage_key}` 字段
2. 通过子 agent 的 `render_md` 把 JSON 渲染成 markdown，写到 `data/plans/{product_key}/{stage_key}.md`
3. 把摘要回传给用户

---

## 2. 12 个子 agent 详细职责

### P 阶段（现状研究 · 3 agent · 无前置依赖）

#### `p_research` — 产品研究员（命令 `/research`）
**唯一职责**：多源采集产品定位、客户需求 (MVP)、对标竞品、关键指标。
**输出**：`positioning` + `mvp_pains` + `key_metrics` + `benchmarks`。
**工具白名单**：`list_products`, `get_product_detail`, `compare_*`, `crawl_product_specs`, `web_search`.

#### `p_teardown` — 拆解分析师（命令 `/teardown`）
**唯一职责**：还原拆解流程 + 装配逆向 + DFA 三问法最少件清单 + 装配反模式。
**方法论**：Boothroyd-Dewhurst 三问法（运动？材料？分离？）。
**输出**：`teardown_sequence` + `assembly_inference` + `min_parts_candidates` + `assembly_pain_points`。
**工具**：`get_motors`, `get_pcb_components`, `match_bom_to_library`, `find_parts`.

#### `p_issues` — 问题诊断师（命令 `/issues`）
**唯一职责**：识别质量问题清单 + 维修维护痛点 + 改善机会方向（**不给解决方案**）。
**输出**：`quality_issues` + `service_issues` + `improvement_opportunities`。
**工具**：`web_search`, `compare_by_spec`.

### L 阶段（精益设计 · 2 agent · DFMA 方法论）

#### `l_dfa` — DFA 优化师（命令 `/dfa`，上游 `p_teardown` + `p_issues`）
**唯一职责**：基于 P 阶段产出，给出 9 项 DFA 优化方向。
**核心铁律**：DFA 中影响最大的单一技术 = 最小化零件数量（行业数据可减 30%~70%）。
**输出**：`dfa_proposals` (9 项 lever) + `fastener_audit` + `standardization_targets` + 节省金额（含装配秒数）。
**工具**：`match_bom_to_library`, `dfma_analysis`.

#### `l_dfm` — DFM 优化师（命令 `/dfm`，上游 `p_teardown`）
**唯一职责**：5 项材料/工艺优化 + **应该成本 (Should Cost)** 建模。
**Should Cost 公式**：材料 + 加工（工时×费率）+ 合理利润（8%~15%）。
**输出**：`dfm_proposals` (5 项 lever) + `should_cost_analysis`（识别报价虚高的件 + 谈判优先级）。
**工具**：`query_materials`, `query_suppliers`, `cut_premium`, `dfma_analysis`.

### A 阶段（先进裁剪 · 2 agent · TRIZ 方法论）

#### `a_function` — 功能建模师（命令 `/function`，上游 `l_dfa` + `l_dfm`）
**唯一职责**：TRIZ 功能-载体建模 + 价值/成本比矩阵 + 过设计/欠设计/冗余/缺失识别。
**输出**：`function_model` (V/C 矩阵) + `over_design` + `under_design` + `function_redundancy` + `function_gaps`。
**工具**：`dfma_analysis`, `vs_compare`, `compare_by_spec`.

#### `a_trim` — 裁剪策略师（命令 `/trim`，上游 `a_function`）
**唯一职责**：三级裁剪决策 + TRIZ 矛盾矩阵 + 架构瓶颈识别。
**输出**：`trim_decisions` (一/二/三级) + `technical_contradictions` (矛盾矩阵+40原理) + `physical_contradictions` (4 种分离方法) + `architectural_bottlenecks`。
**工具**：`dfma_analysis`, `cut_premium`, `vs_compare`.

### N 阶段（价值创新 · 3 agent）

#### `n_fos` — 功能创新搜索师（命令 `/fos`，上游 `a_trim`）
**唯一职责**：跨领域 FOS (Function-Oriented Search) 找功能替代方案。
**方法**：抽象功能 → 跨领域映射 → 方案吸收 → 落实新方案。
**输出**：`fos_proposals`（每条含跨领域启发 + 候选替代 + 关键技术 + 集成难度 + 成本对比 + 风险）。
**工具**：`web_search`, `query_materials`, `query_suppliers`.

#### `n_patent` — 专利规避师（命令 `/patent`，上游 `n_fos`）
**唯一职责**：对 `/fos` 候选方案做专利检索 + 权利要求映射 + **工程层规避**方案。
**⚠️ 非法律意见**——最终须专业 IP 律师评估。
**输出**：`patent_landscape` + `risk_patents` + `design_around_options` + `needs_lawyer_review`。
**工具**：`web_search`, `web_fetch`.

#### `n_trend` — 趋势分析师（命令 `/trend`，**无前置依赖**）
**唯一职责**：S 曲线分析 + TRIZ 系统进化方向 + 四新设计 + 3 年路线图。
**输出**：`s_curve_analysis` + `evolution_directions` (理想化/动态化/可控性/集成化/智能化) + `four_new` + `innovation_roadmap_3y`。
**工具**：`web_search`, `query_materials`, `vs_compare`.

### S 阶段（体系建设 · 2 agent · 上游 `a_trim` + `n_fos`）

#### `s_platform` — 平台架构师（命令 `/platform`）
**唯一职责**：从产品矩阵视角做产品复杂性管理 + 平台化模块化设计。
**输出**：`complexity_assessment` (SKU/共件率/平台化分) + `platform_candidates` + `platform_designs` + `complexity_process`（流程建议）。
**工具**：`list_products`, `find_parts`, `compare_cost_benchmark`.
**参考**：汽车业大众 MQB 平台。

#### `s_costsystem` — 成本体系构建师（命令 `/costsystem`）
**唯一职责**：组织/设施/能力/数据/流程 5 维体系建设方案，含 PLANS 嵌入 NPI Gates。
**输出**：5 维结构化方案 + NPI Gate 节点定义。
**工具**：`list_products`, `find_parts`, `export_framework`, `web_search`.

---

## 3. 阶段依赖关系图

```
（无依赖，可并行）             （L 阶段）
  /research ──────┐
  /teardown ──────┼──→ /dfa  (need teardown + issues)
  /issues ────────┤      ├──→ /function ──→ /trim
                  └──→ /dfm  (need teardown)
                                                 │
                            ┌────────────────────┤
                            ▼                    ▼
                          /fos  ──→ /patent     /platform
                                                /costsystem

  /trend ────────────────────（独立，任何时候可跑）
```

依赖在 `core/plans_store.py` 的 `STAGE_DEPS` 集中维护。运行时若依赖未满足，主 agent 返回 `status: blocked` + `missing_prereqs`。

---

## 4. 主 agent 工具入口（共 15 个 plans_* 工具）

| 工具 | 输入 | 行为 |
|------|------|------|
| `plans_research` | `{product_key}` | 跑 P 阶段产品研究员 |
| `plans_teardown` | `{product_key}` | 跑 P 阶段拆解分析师 |
| `plans_issues` | `{product_key}` | 跑 P 阶段问题诊断师 |
| `plans_dfa` | `{product_key}` | 跑 L 阶段 DFA 优化师 |
| `plans_dfm` | `{product_key}` | 跑 L 阶段 DFM 优化师 |
| `plans_function` | `{product_key}` | 跑 A 阶段功能建模师 |
| `plans_trim` | `{product_key}` | 跑 A 阶段裁剪策略师 |
| `plans_fos` | `{product_key}` | 跑 N 阶段功能创新搜索师 |
| `plans_patent` | `{product_key}` | 跑 N 阶段专利规避师 |
| `plans_trend` | `{product_key}` | 跑 N 阶段趋势分析师 |
| `plans_platform` | `{product_key}` | 跑 S 阶段平台架构师 |
| `plans_costsystem` | `{product_key}` | 跑 S 阶段成本体系构建师 |
| `plans_run_all` | `{product_key, stages?}` | 串行跑全 12 阶段 + overview.md |
| `plans_status` | `{product_key}` | 查阶段进度 |
| `plans_overview` | `{product_key}` | 重拼 overview.md |

每个 `plans_*` 工具内部都通过 `_run_plans_stage(stage, product_key)` 委托：
1. 检查依赖（`plans_store.missing_deps`）
2. 加载子 agent 模块（`_stage_module(stage)`）
3. 用 `_make_client()` 启动子 agent messages 循环
4. 抽取 JSON → render → 保存

---

## 5. 文件布局

```
unit-bot/
├── agent.py                      # 主 orchestrator（保留）
├── 价值设计流程PLANS.md            # PLANS 方法论原文（事实来源）
│
├── agents/                       # 12 子 agent
│   ├── README.md                 # 子 agent 集合说明
│   ├── base.py                   # run_subagent + extract_json
│   │
│   ├── p_research/               # ↓ 12 子目录，每个 5 文件 ↓
│   │   ├── __init__.py           # 导出 STAGE / SYSTEM_PROMPT / ALLOWED_TOOLS / render_md / build_user_input
│   │   ├── prompt.md             # system prompt
│   │   ├── tools.py              # ALLOWED_TOOLS
│   │   ├── schema.py             # build_user_input + OUTPUT_SCHEMA_DOC
│   │   └── render.py             # render_md
│   ├── p_teardown/               # 同上结构
│   ├── p_issues/
│   ├── l_dfa/
│   ├── l_dfm/
│   ├── a_function/
│   ├── a_trim/
│   ├── n_fos/
│   ├── n_patent/
│   ├── n_trend/
│   ├── s_platform/
│   └── s_costsystem/
│
├── core/
│   └── plans_store.py            # STAGES (12) + STAGE_TITLES + STAGE_PHASE + STAGE_DEPS + save_stage / render_overview
│
├── docs/
│   └── agents_architecture.md    # 你正在看
│
└── data/
    └── plans/
        ├── plans_db.json         # 第 6 数据库：所有机型 12 阶段产出（结构化）
        └── {slug}/               # 每机型 12 份报告 + overview
            ├── p_research.md
            ├── p_teardown.md
            ├── p_issues.md
            ├── l_dfa.md
            ├── l_dfm.md
            ├── a_function.md
            ├── a_trim.md
            ├── n_fos.md
            ├── n_patent.md
            ├── n_trend.md
            ├── s_platform.md
            ├── s_costsystem.md
            └── overview.md
```

**`plans_db.json` 结构**：

```json
{
  "石头G30SPro": {
    "product_key": "石头G30SPro",
    "stages": {
      "p_research":   { "ran_at": "2026-05-09T...", "data": {...}, "report_path": "..." },
      "p_teardown":   { ... },
      "p_issues":     { ... },
      "l_dfa":        { ... },
      "l_dfm":        { ... },
      "a_function":   { ... },
      "a_trim":       { ... },
      "n_fos":        { ... },
      "n_patent":     { ... },
      "n_trend":      { ... },
      "s_platform":   { ... },
      "s_costsystem": { ... }
    }
  }
}
```

---

## 6. 子 agent 共同约定

- **只读不写业务库**：子 agent 不调用 `save_product` / `update_spec` / `upsert_component` 等写操作。所有写库由主 agent 通过 `plans_store.save_stage()` 统一执行。
- **输出格式**：必须以一段 ` ```json ` 代码块结束，schema 见各 agent 的 `prompt.md` 末尾。
- **JSON 提取**：`base.py` 的 `extract_json` 优先解析 ` ```json ``` 块，失败则尝试整段最大花括号对象。
- **失败兜底**：若没返回有效 JSON，主 agent 返回 `status: error`，**不**污染 plans_db.json。
- **OpenClaw 兼容**：`web_search` / `web_fetch` 是 Anthropic 服务端工具，OpenClaw 后端会被 `_make_client()` 自动剔除。

---

## 7. 用户命令到工具的映射

| 用户命令 | 调用工具 |
|---------|---------|
| `/research <product>` | `plans_research` |
| `/teardown <product>` | `plans_teardown` |
| `/issues <product>` | `plans_issues` |
| `/dfa <product>` | `plans_dfa` |
| `/dfm <product>` | `plans_dfm` |
| `/function <product>` | `plans_function` |
| `/trim <product>` | `plans_trim` |
| `/fos <product>` | `plans_fos` |
| `/patent <product>` | `plans_patent` |
| `/trend <product>` | `plans_trend` |
| `/platform <product>` | `plans_platform` |
| `/costsystem <product>` | `plans_costsystem` |
| `/plans <product>` | `plans_run_all`（串行全 12） |
| `/plans status <product>` | `plans_status` |
| `/plans overview <product>` | `plans_overview` |

---

## 8. 与旧 5-agent 架构的迁移

| 旧 (5-agent) | 新 (12-agent) | 说明 |
|------------|---------------|------|
| `/plans p` | `/research` + `/teardown` + `/issues` | P 阶段拆 3 个子角色 |
| `/plans l` | `/dfa` + `/dfm` | L 阶段拆 DFA / DFM 双轮 |
| `/plans a` | `/function` + `/trim` | A 阶段功能分析 vs 裁剪策略分离 |
| `/plans n` | `/fos` + `/patent` + `/trend` | N 阶段创新 / 专利 / 趋势分离 |
| `/plans s` | `/platform` + `/costsystem` | S 阶段架构 / 体系建设分离 |
| `/dfma` | 拆为 L+A 阶段 | 已废除：DFMA 实质是 DFA+DFM+功能分析 |
| `/cut` | 合并进 `/dfm` 的 Should Cost | 已废除：件级溢价识别由 Should Cost 谈判覆盖 |
| `/product` | `/research` | 改名：术语对齐文档 |

---

## 9. 风险与权衡

- **延迟**：12 个子 agent 串行 = 12 倍 latency。`/plans <product>` 全流程预计 5-15 分钟。如果用户希望并行，主 agent 可改成 `asyncio.gather` 跑相互无依赖的阶段（如 P 阶段 3 个 agent 完全可并行），但 OpenClaw 后端是否支持并发需测；先做串行。
- **token 成本**：每个子 agent 独立上下文，不共享对话历史 → 比单 agent 贵 ~12x。补偿：每个子 agent 的 system prompt 只装本阶段需要的 4-14 个工具（vs 主 agent 46 个），prompt 体积小很多。
- **JSON 提取脆弱**：模型偶尔不严格按 schema。容错：先尝试 `\`\`\`json` 块；失败则用 `extract_json` 兜底。
- **主 agent 仍是 orchestrator，不是真正多 agent 框架**：没引入 LangGraph / CrewAI 等依赖；保持轻。如果以后要 DAG 编排再升级。
- **专利规避 ≠ 法律意见**：`n_patent` 在 prompt 和 render 都明确标注 ⚠️，输出包含 `needs_lawyer_review` 字段。
