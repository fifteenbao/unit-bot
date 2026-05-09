---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"]}}
---

# unit-bot — 扫地机器人 PLANS 价值设计平台

面向产品 / 成本 / 研发团队，整个项目以 **PLANS 价值设计流程**（**P** 现状研究 → **L** 精益设计 → **A** 先进裁剪 → **N** 价值创新 → **S** 体系建设）为骨架，把竞品拆机分析、BOM 成本核算、降本优化、创新研判、体系建设串成一条工作流。支持接入 OpenClaw / 飞书 / Slack，也可直接 CLI 使用。

---

## 命令速查（PLANS 12 子 agent 架构）

PLANS 拆为 12 个独立子 agent，每个职责单一、上下游清晰。

### P · 现状研究（3 agent · 无前置依赖）

| 命令 | Agent | 职责 | 示例 |
|------|-------|------|------|
| `/research <product>` | 产品研究员 | 产品定位 + MVP 客户需求 + 关键指标 + 对标 | `/research 追觅 X50 Ultra` |
| `/teardown <product>` | 拆解分析师 | 拆解流程 + 装配逆向 + DFA 三问法最少件 | `/teardown 石头 G30S Pro` |
| `/issues <product>` | 问题诊断师 | 质量问题 + 维修维护 + 改善机会方向 | `/issues 石头 G30S Pro` |

### L · 精益设计（2 agent · DFMA）

| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/dfa <product>` | DFA 优化师 | 9 项装配优化 + 紧固件审计 + 标准化 | `/teardown` + `/issues` |
| `/dfm <product>` | DFM 优化师 | 5 项材料/工艺优化 + 应该成本 (Should Cost) | `/teardown` |

### A · 先进裁剪（2 agent · TRIZ）

| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/function <product>` | 功能建模师 | TRIZ 功能-载体建模 + 价值/成本比矩阵 | `/dfa` + `/dfm` |
| `/trim <product>` | 裁剪策略师 | 三级裁剪 + TRIZ 矛盾矩阵 + 架构瓶颈 | `/function` |

### N · 价值创新（3 agent）

| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/fos <product>` | 功能创新搜索师 | 跨领域 FOS 功能替代方案 | `/trim` |
| `/patent <product>` | 专利规避师 | 专利检索 + 工程层规避（**非法律意见**） | `/fos` |
| `/trend <product>` | 趋势分析师 | S 曲线 + 系统进化 + 四新设计 + 3 年路线图 | 无 |

### S · 体系建设（2 agent）

| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/platform <product>` | 平台架构师 | 产品复杂性 + 平台化设计 + 流程 | `/trim` + `/fos` |
| `/costsystem <product>` | 成本体系构建师 | 组织/设施/能力/数据/流程 5 维体系 | `/trim` + `/fos` |

### 编排器

| 命令 | 用途 | 示例 |
|------|------|------|
| `/plans <product>` | 串行跑全 12 阶段（按依赖顺序）+ overview.md | `/plans 石头 G30S Pro` |
| `/plans status <product>` | 查 12 阶段进度 | `/plans status 石头 G30S Pro` |
| `/plans overview <product>` | 重新拼 overview.md（不重跑） | `/plans overview 石头 G30S Pro` |

### 已废除的旧用户命令

`/bom` `/vs` `/find` `/framework` `/cut` `/dfma` `/product` 已全部废除——其底层工具（`generate_teardown_csv` / `vs_compare` / `find_parts` / `export_framework` / `cut_premium` 等）已合并到 12 个子 agent 的工具白名单，由 agent 自主调用。用户**只用 12 个 PLANS 命令 + `/plans` 编排器**。

唯一例外：FCC 数据采集仍需用户 shell 跑 `python scripts/fetch_fcc.py find/ocr "<品牌> <型号>"`（涉及文件下载和视觉 OCR，不在 agent 工具集里）。

---

## 数据分类

系统维护 9 个数据库：

| 数据库 | 文件 | 角色 | 维护方式 |
|--------|------|------|---------|
| **① 产品规格库** | `data/products/products_db.json` | "是什么" — MSRP / 规格 / 功能 | `import_products.py` / `save_product` |
| **② 拆机档案** | `data/teardowns/*.csv` + `fcc/{slug}/*` | "用了什么件" — 元器件 BOM | `fetch_fcc.py` + `gen_teardown.py` 自动产出 |
| **③ 标准件库** | `data/lib/components_lib.csv` | "值多少钱" — 跨机型聚合定价 | `build_components.py`（仅接受 `fcc/teardown/confirmed`） |
| **④ 材料库** | `data/lib/materials.csv` | "原材料单价" — 22 种原料的 price_min/max/mid | 直接编辑 CSV |
| **⑤ 供应商应该成本库** | `data/lib/suppliers.csv` | "谁在供货" + 应该成本 — 37 家供应商的档次/地区/采购条件 | 直接编辑 CSV |
| **⑥ 工艺库** | `data/lib/processes.csv` _(待建)_ | "怎么做出来" — 注塑/CNC/钣金/压铸的工时和工时费率 | 待建 schema |
| **⑦ 模具库** | `data/lib/molds.csv` _(待建)_ | "模具摊销多少" — 模具开发成本 / 寿命 / 单件摊销 | 待建 schema |
| **⑧ 加工工具库** | `data/lib/tooling.csv` _(待建)_ | "用什么夹具刀具" — 工装夹具、刀具、量具的单件折旧 | 待建 schema |
| **⑨ PLANS 研究库** | `data/plans/plans_db.json` + `data/plans/{slug}/*.md` | "做过哪些降本研究" — 12 子 agent 产出 | `plans_store.save_stage` 统一写入 |

> **应该成本（Should Cost）公式** = ④ 材料 + ⑥ 加工工时×费率 + ⑦ 模具摊销 + ⑧ 工具折旧 + 合理利润 (8%~15%)
> 这是 `/dfm` 子 agent 的核心建模逻辑。⑥/⑦/⑧ 三库 schema 待建中，先以 LLM 推理 + 行业基准估算填充。

---

## 材料库与供应商库

Agent 工具 `query_materials` 和 `query_suppliers` 直接读取 CSV，由子 agent 在以下场景自动调用：

| 场景 | 工具 | 典型调用 |
|------|------|---------|
| `/teardown` 供应链分析 | `query_suppliers` | `query_suppliers(category="compute_electronics")` |
| `/dfm` Should Cost 替代供应商 | `query_suppliers` | `query_suppliers(keyword="SoC", tier="二线")` |
| `/dfm` structure_cmf 材料成本分解 | `query_materials` | `query_materials(bom_bucket="structure_cmf")` |
| `/fos` 找新材料候选 | `query_materials` | `query_materials(keyword="HEPA")` |

**`query_materials` 过滤参数**：
- `keyword`：在名称/用途/备注中模糊搜索（如 `"ABS"` / `"拖布"` / `"HEPA"`）
- `mat_type`：工程塑料 / 弹性体 / 金属 / 滤材 / 织物 / 泡棉 / 涂料 / 复合材料
- `bom_bucket`：structure_cmf / cleaning / compute_electronics / dock_station / energy

**`query_suppliers` 过滤参数**：
- `keyword`：供应商名称或产品关键词（如 `"Rockchip"` / `"BLDC"` / `"LPDDR"`）
- `category`：compute_electronics / perception / power_motion / energy / structure_cmf / cleaning
- `tier`：一线 / 二线 / 三线
- `region`：大陆 / 台湾 / 日本 / 韩国 / 欧洲 / 美国

---

## 命令详解

### PLANS 12-Agent 架构

每个 PLANS 子 agent 是一个独立模块，目录结构 `agents/<stage_key>/`：
- `prompt.md` — system prompt（独立 markdown）
- `tools.py` — `ALLOWED_TOOLS` 工具白名单
- `schema.py` — `build_user_input` + 输出 JSON schema 文档
- `render.py` — `render_md` 把 JSON 渲染成报告
- `__init__.py` — 重新导出标准接口

**架构原则**：
- 主 agent (orchestrator) 不做 PLANS 调研，只调用 `plans_*` 工具调度子 agent。
- 每个子 agent 单一职责，输入输出严格定义。
- 子 agent **只读不写**业务库；所有写库由 `plans_store.save_stage` 统一进 `plans_db.json`。
- 阶段依赖关系由 `core/plans_store.py` 的 `STAGE_DEPS` 集中维护，跨阶段依赖未满足时自动 `blocked`。
- 详细架构：[docs/agents_architecture.md](docs/agents_architecture.md)

| 阶段 | 子 agent (12) | 命令 | 上游 |
|------|---------------|------|------|
| **P** 现状研究 | `p_research` (产品研究员) | `/research` | 无 |
| | `p_teardown` (拆解分析师) | `/teardown` | 无 |
| | `p_issues` (问题诊断师) | `/issues` | 无 |
| **L** 精益设计 | `l_dfa` (DFA 优化师) | `/dfa` | `/teardown`+`/issues` |
| | `l_dfm` (DFM 优化师) | `/dfm` | `/teardown` |
| **A** 先进裁剪 (TRIZ) | `a_function` (功能建模师) | `/function` | `/dfa`+`/dfm` |
| | `a_trim` (裁剪策略师) | `/trim` | `/function` |
| **N** 价值创新 | `n_fos` (功能创新搜索师) | `/fos` | `/trim` |
| | `n_patent` (专利规避师) | `/patent` | `/fos` |
| | `n_trend` (趋势分析师) | `/trend` | 无 |
| **S** 体系建设 | `s_platform` (平台架构师) | `/platform` | `/trim`+`/fos` |
| | `s_costsystem` (成本体系构建师) | `/costsystem` | `/trim`+`/fos` |

---

### P 阶段命令详解（3 agent）

#### `/research <product>`
> `/research 追觅 X50 Ultra`

P 阶段产品研究员：多源采集产品定位、客户需求 (MVP)、对标竞品、关键指标。
**职责单一**：不读拆机数据，不算成本。

#### `/teardown <product>`
> `/teardown 石头 G30S Pro`

P 阶段拆解分析师：还原拆解流程、推断装配顺序、用 Boothroyd-Dewhurst 三问法识别可合并件、列出装配反模式（焊接/粘接/螺纹紧固/单独动作/人体工学问题）。
读取 `get_motors` + `get_pcb_components` + FCC OCR 数据。

#### `/issues <product>`
> `/issues 石头 G30S Pro`

P 阶段问题诊断师：扫描用户评论、维修视频，识别质量问题清单 + 维修维护痛点 + 改善机会方向。
**不给解决方案**——那是 L/A/N 阶段的活。

---

### L 阶段命令详解（2 agent · DFMA）

#### `/dfa <product>`
> `/dfa 卧安 K10+ Pro Combo`

L 阶段 DFA 优化师：基于 P 阶段产出，给出 9 项 DFA 优化方向：
1. 最小件合并（Boothroyd-Dewhurst 三问法）
2. 紧固件减少
3. 自定位防呆设计
4. 自固定设计
5. 防止欠/过约束
6. 单独装配动作消除
7. 焊接/粘接/螺纹紧固消除
8. 解决人体工学问题
9. 标准化设计

每条建议附 **预估节省（元/台 + 装配秒数）+ 主要风险**。

#### `/dfm <product>`
> `/dfm 卧安 K10+ Pro Combo`

L 阶段 DFM 优化师：5 项材料/工艺优化方向 + 核心件**应该成本 (Should Cost)** 建模：

| 优化方向 |
|---------|
| 材料替代（PC+ABS → PP；玻纤增强 → 普通工程塑料）|
| 工艺改变（CNC → 注塑、喷涂 → 免喷涂塑料）|
| 加工精度放宽（±0.5mm = 1× vs ±0.01mm = 10~20×）|
| 表面处理简化 |
| 结构简化 |

**Should Cost 公式**：材料成本 + 加工成本（工时×费率）+ 合理利润（8%~15%）。
对比当前报价 → 识别**报价虚高**的件，列出谈判优先级。

---

### A 阶段命令详解（2 agent · TRIZ）

#### `/function <product>`
> `/function 石头 G30S Pro`

A 阶段功能建模师：用 TRIZ 功能分析法把产品建模为「功能-载体」对应表。
- 每个功能/载体打 V (客户感知价值) + C (成本占比) → V/C 比。
- V/C < 0.8 = 过设计；V/C > 1.2 = 欠设计。
- 同时识别**功能冗余**（多载体实现同一功能）和**功能缺失**（用户期待但未实现）。

#### `/trim <product>`
> `/trim 石头 G30S Pro`

A 阶段裁剪策略师：基于 `/function` 的价值矩阵做激进裁剪 + TRIZ 矛盾矩阵：

**三级裁剪**：
- 一级：裁剪 V<0.5 的功能缺陷
- 二级：裁剪 V/C<1 的组件
- 三级：激进裁剪（载体彻底替换，如去基站化）

**TRIZ 矛盾**：
- 技术矛盾（吸力↑ → 噪声↑）→ 用 39×39 矛盾矩阵给候选发明原理
- 物理矛盾（拖布既要湿又要干）→ 4 种分离方法（时间/空间/条件/系统）
- 架构瓶颈识别 → N 阶段 FOS 入口

---

### N 阶段命令详解（3 agent）

#### `/fos <product>`
> `/fos 石头 G30S Pro`

N 阶段功能创新搜索师：基于 `/trim` 的架构瓶颈做**跨领域功能搜索**（FOS）。
- 把功能抽象为跨行业通用语（"扫地机的尘气分离" → "连续流体中固体颗粒分离"）
- 找其他行业的解决方案（工业除尘 / 抽油烟机旋风分离 / 真空吸料机）
- 评估技术/供应商/集成难度/成本对比/风险

#### `/patent <product>`
> `/patent 石头 G30S Pro`

N 阶段专利规避师：对 `/fos` 候选方案做专利检索 + 权利要求映射 + 工程层规避方案。
**⚠️ 工程意见，非法律意见。最终是否构成侵权由专业 IP 律师评估。**

规避策略（按风险从低到高）：
- 替换技术手段（最安全）
- 改变结构特征（中等）
- 改变实施场景（中等）
- 不做该功能（最安全但损失功能）

#### `/trend <product>`
> `/trend 石头 G30S Pro`

N 阶段趋势分析师：S 曲线分析 + 系统进化方向 + 四新设计 + 3 年路线图。

**TRIZ 系统进化方向**（产品朝"理想化↑"演进）：
- 理想化（基站消失/雷达消失）
- 动态化（固定吸口 → 动态张紧）
- 可控性（全功率清洁 → 按地面材质变功率）
- 集成化（多板合一）
- 智能化（端侧大模型）

**S 曲线**：扫地机当前在成长期晚期/成熟期早期，需要识别下一条 S 曲线种子。

**无前置依赖**——可独立跑。

---

### S 阶段命令详解（2 agent）

#### `/platform <product>`
> `/platform 石头 G30S Pro`

S 阶段平台架构师：从**整个产品矩阵**视角做产品复杂性管理 + 平台化设计。
- 复杂性评分（SKU 数 / 共件率 / 平台化程度）
- 平台化候选识别（按"投入产出比"排序）
- 具体平台设计（覆盖机型 / 可变参数 / 接口标准）
- 复杂性管理流程（立项守门 / 共件率 KPI / 退役机制）

参考案例：汽车业大众 MQB 平台。

#### `/costsystem <product>`
> `/costsystem 石头 G30S Pro`

S 阶段成本体系构建师：5 维体系建设方案：

| 维度 | 内容 |
|------|------|
| 组织 | DFMA / 成本工程团队、岗位职责、跨部门会议机制、KPI |
| 设施 | 拆解实验室、成本数据库平台、Should Cost 建模工具、看板 |
| 能力 | DFMA / TRIZ / Should Cost 培训路线、内部认证 |
| 数据 | 数据库更新频率、责任人、可信度等级、共享机制 |
| 流程 | PLANS 嵌入 NPI Gates（立项 → 概念 → 设计 → 模具 → 量产 → 退市） |

---

### 数据采集（用户手动）

#### FCC 文档检索 + PCB 芯片 OCR
```bash
python scripts/fetch_fcc.py find "石头 G30S Pro"   # 查 FCC ID 和文档链接（不下载）
python scripts/fetch_fcc.py ocr  "石头 G30S Pro"   # 下载 PDF + 逐页视觉 OCR 识别芯片丝印
```

涉及文件下载和视觉 OCR，不在 agent 工具集里——`/teardown` 子 agent 调研时若发现 PCB 数据缺失，会提示用户先跑此命令。

> 其余底层数据采集 / 查询工具（`generate_teardown_csv` / `vs_compare` / `find_parts` / `export_framework` 等）已合并到 12 个子 agent 的工具白名单，由 agent 自主调用，**不向用户暴露为命令**。

---

### 编排器命令详解

#### `/plans <product>` — 串行跑全 12 阶段
> `/plans 石头 G30S Pro`

按依赖顺序串行 P→L→A→N→S（12 个 agent），全部完成后生成 `data/plans/{slug}/overview.md`。
任一阶段 blocked（依赖未满足）会跳过但不停；任一阶段 error 会停止后续。

#### `/plans status <品牌> <型号>` — 查阶段进度
返回每个阶段是否完成 + 完成时间 + 报告路径。

#### `/plans overview <品牌> <型号>` — 重新拼 overview.md
不重跑 agent，只把已有阶段产出合并为总览。

---

## 维护入口

| 入口 | 场景 |
|------|------|
| `core/bom_8bucket_framework.json` | 调整桶定义 / 典型子项 / 基准占比 |
| `data/lib/components_lib.csv` | 日常价格维护（`cost_min/cost_max`） |
| `data/lib/standard_parts.json` | 未收录件基准价 fallback |
| `data/products/model_aliases.csv` | 国内/海外型号映射 |
| `data/products/products.csv` | 新增机型规格 |

---

## Pipeline 详细：`gen_teardown.py` 4-Stage + 4级成本结构

按 **4级成本结构** 组织：一级(5大成本类) → 二级(7桶, 全部归入硬件物料) → 三级(功能模块) → 四级(组件/最小计价单元)。

| Stage | 职责 | 关键产出 |
|-------|------|---------|
| **0 FCC 上游** | 自动载入 `fcc/{slug}/*_fcc_*.csv`（有则注入，无则跳过） | 已知 FCC 件不重复爬取 |
| **1 Discovery** | 多源调研爬元器件型号；prompt 注入 4级结构 + 7桶定义 + Stage 0 已知件 | `bom_bucket + name + model + spec + confidence + source_url`；空结果自动降级为 framework_fill |
| **2 Enrichment** | SoC 推导伴随件：识别到 RK3588S 等自动补 PMIC/RAM/ROM/AI 授权 | 补齐易漏配套件 |
| **~ Normalize** | LLM 自创桶名（如 `perception_system`）映射回 framework 7 个合法 key | 兜底保护 |
| **3 Coverage Audit** | 从产品数据库检测硬件特征（基站/上下水/升降雷达/拖布延边等），按 condition 过滤 typical_items 后逐桶检查覆盖缺口，补缺行写入 CSV（`confidence=framework_fill`，`_price_src` 标注来源） | 缺失项清单 + 自动补齐行 |
| **4 Aggregate & Bias** | 三级查价（`components_lib` → `standard_parts` → 桶兜底）+ 辅料组装估算 + 传感器分档；桶占比 vs 基准 ±tolerance + BOM/MSRP 诊断 + **一级成本结构** (5大类, BOM实测+固定参考) | BOM合计 · 桶占比偏差告警 · 整机全成本估算 · DFA 组装难度分 |

**Stage 1 兜底**：未找到公开拆机资料时自动降级为 `framework_fill`，按 `typical_items` 生成基线 BOM（全部标记 `confidence=estimate`），不中断流程。

**Stage 4 一级成本结构**：硬件物料(7桶) 用 BOM 实测值，其余 4 项（人工+机器折旧 / 销售+管理费用 / 研发均摊 / 仓储物流售后）按档位固定参考值。非硬件成本单台相对固定，硬件物料是唯一高度可变项。

> 更新 `components_lib.csv` 的 `cost_min/cost_max`，下次跑 Stage 4 自动生效，无需重启。

---

## FCC 采集详细

**支持品牌**：石头 Roborock · 追觅 Dreame · 科沃斯 Ecovacs · 云鲸 Narwal · SwitchBot 卧安 · 3irobotics 杉川 · Eufy 安克 · Xiaomi 小米 · iRobot

```bash
# Step 1：查文档链接（不下载，供人工核查）
python scripts/fetch_fcc.py find "石头G30S Pro"
python scripts/fetch_fcc.py find "科沃斯X8 Pro" --fcc-id 2A6HE-DEX8PRO
python scripts/fetch_fcc.py find "石头G30S Pro" --force

# Step 2：下载 PDF + OCR
python scripts/fetch_fcc.py ocr "石头G30S Pro"
python scripts/fetch_fcc.py ocr "石头G30S Pro" --force
AIHUBMIX_API_KEY=xxx AIHUBMIX_MODEL=gpt-4o python scripts/fetch_fcc.py ocr "石头G30S Pro"
```

产出路径：`data/teardowns/fcc/{slug}/links.json`（find）· `latest.json` + `pdfs/` + `{slug}_fcc_{date}.csv`（ocr）。

---

## BOM 7 桶框架

单一事实源：`core/bom_8bucket_framework.json`，通过 `core/bucket_framework.py` 加载。修改一处，gen_teardown / analyze / export_csv 四处自动同步。

| # | 桶 | 核心内容 | 行业基准 | 价值权重 (entry/mid/flagship) |
|---|---|---------|---------|-------|
| 1 | 算力与电子 | SoC · MCU · Wi-Fi/BT · PMIC · RAM/ROM · PCB · 阻容 | 13% (10–20%) | 0.5 / 0.7 / 0.9 |
| 2 | 感知系统 | LDS · ToF · 前视线激光 · IMU · 沿墙 · 超声波 · 碰撞 | 16% (12–25%) | 0.6 / 0.85 / 1.0 |
| 3 | 动力与驱动 | 主机吸尘风机 · 驱动轮/履带 · 边轮 · 万向轮 · 越障升降 | 11% (8–15%) | 0.6 / 0.75 / 0.85 |
| 4 | 清洁功能 | 拖布本体 · 滚刷 · 边扫 · 主机水箱/尘盒 · 清水泵 | 20% (14–30%) | 0.7 / 0.9 / 1.0 |
| 5 | 基站系统 | 外壳 · 电源 · 集尘 · 清水/污水桶 · PTC · 顶杆 · PCBA | 24% (15–35%) ¹ | 0.0 / 0.7 / 1.0 |
| 6 | 能源系统 | 锂电池包（电芯 + BMS + 封装） | 7% (3–10%) | 0.8 / 0.7 / 0.6 |
| 7 | 整机结构 CMF | 上盖/底盘 · CMF 喷涂 · 模具摊销 · 紧固件 | 13% (10–20%) | 0.5 / 0.65 / 0.8 |

> ¹ 基站占比分档：纯充电桩 ~5%、含换水 +10%、含集尘 +8%、含自清洗 +5%。T80S 实测 dock_station 占比 ~30%（旗舰全功能基站）。
> ² 原第 8 桶「MVA+软件授权」已拆分到一级成本大类：组装人工 → 人工+机器折旧、SLAM版税/OS授权 → 研发均摊、包装材料/物流运保 → 仓储物流成本。
> 整机 BOM/MSRP 比例常见 **25–40%**（旗舰机偏上限）。基准数据来源：开源证券·科沃斯T80S拆解（2024）。

### 桶字段结构（DFMA 相关）

每个桶除 `industry_pct_range` / `typical_items` / `boundary_notes` 外，还携带以下 DFMA 字段：

| 字段 | 类型 | 作用 |
|------|------|------|
| `user_value_weight.note` | string | 价值权重打分的定性说明（仅供人工审核，不参与计算） |
| `user_value_weight.entry` | float `0~1` | 入门档（< ¥2000 / 无基站）下用户对该桶的感知价值权重 |
| `user_value_weight.mid` | float `0~1` | 中档（¥2000~4000）下的价值权重 |
| `user_value_weight.flagship` | float `0~1` | 旗舰档（≥ ¥4000 / 全功能基站）下的价值权重 |
| `dfma_levers` | array | 该桶可用的 DFMA 设计抓手清单（降级/合并/工艺简化） |

> 同一个桶在不同档位的权重通常不同。例如能源桶 `entry=0.8 / flagship=0.6`：入门机靠续航完成全屋清扫，旗舰机有基站随时回充。`/dfma` 命令按产品档位自动选取对应权重计算价值成本比。

---

## 置信度层级

| 来源 | `confidence` | 用途 |
|------|---|------|
| 产品数据库（人工/CSV） | `database` | 规格 / 价格 / 功能 |
| 实物拆机 CSV | `teardown` | PCB 芯片 / 电机 / 传感器 |
| FCC 照片识别 | `fcc` | PCB 芯片（与 BOM 流程解耦） |
| 网络调研 | `web` | 规格层（吸力/续航/布尔功能） |
| 同平台推断 | `inferred` | SoC 伴随件（Stage 2 产出） |
| 行业基准估算 | `estimate` | 无拆机数据时的 BOM 成本 |
| 框架补缺 | `framework_fill` | Stage 3 自动补缺，按特征过滤+典型子项估算 |

> `inferred` 数据需实物拆机核实后方可升级为 `confirmed`。
