---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"]}}
---

# unit-bot — 扫地机器人 BOM 成本分析与技术选型

面向产品 / 成本 / 研发团队，提供扫地机器人（RVC）品类的竞品拆机分析、BOM 成本核算、降本优化建议。支持接入 OpenClaw / 飞书 / Slack，也可直接 CLI 使用。

---

## 命令速查

### 核心命令

| 命令 | 用途 | 示例 |
|------|------|------|
| `/bom <品牌> <型号>` | BOM 完整分析（成本数据 + 供应链/风险，不含降本建议） | `/bom 石头 G30S Pro` |
| `/dfma <品牌> <型号>` | DFMA 功能-成本矩阵 + 设计抓手 + 整机降本潜力 | `/dfma 卧安 K10+ Pro Combo` |
| `/product <品牌> <型号>` | 多源采集规格参数（vacuumwars/中关村/电商），录入产品库 | `/product 追觅 X50 Ultra` |
| `/fcc find <品牌> <型号>` | 查找 FCC 文档链接（不下载） | `/fcc find 石头 G30S Pro` |
| `/fcc ocr <品牌> <型号>` | 下载 PDF + OCR 识别 PCB 芯片丝印 | `/fcc ocr 石头 G30S Pro` |

### 高级命令（不常用）

| 命令 | 用途 | 示例 |
|------|------|------|
| `/cut <品牌> <型号>` | 单点溢价件识别（与 /dfma 互补） | `/cut 石头 G20S` |
| `/vs <A> vs <B> [--bucket <桶>]` | 子系统 / 整机对标 | `/vs 科沃斯X8Pro vs 石头S8MaxV --bucket dock_station` |
| `/find <关键词\|桶>` | 数据库直查 | `/find SoC`（或 `/find compute_electronics`） |
| `/framework` | 导出 7 桶对账 CSV | `/framework` |

---

## 数据分类

| 数据库 | 文件 | 角色 | 维护方式 |
|--------|------|------|---------|
| **① 产品规格库** | `data/products/products_db.json` | "是什么" — MSRP / 规格 / 功能 | `import_products.py` / `save_product` |
| **② 拆机档案** | `data/teardowns/*.csv` + `fcc/{slug}/*` | "用了什么件" — 元器件 BOM | `/fcc` + `gen_teardown.py` 自动产出 |
| **③ 标准件库** | `data/lib/components_lib.csv` | "值多少钱" — 跨机型聚合定价 | `build_components.py`（仅接受 `fcc/teardown/confirmed`） |
| **④ 材料库** | `data/lib/materials.csv` | "原材料单价" — 22种原料的 price_min/max/mid | 直接编辑 CSV |
| **⑤ 供应商库** | `data/lib/suppliers.csv` | "谁在供货" — 37家供应商的档次/地区/采购条件 | 直接编辑 CSV |

---

## 材料库与供应商库

Agent 工具 `query_materials` 和 `query_suppliers` 直接读取 CSV，无需命令触发，在以下场景自动调用：

| 场景 | 工具 | 典型调用 |
|------|------|---------|
| `/bom` Step 6 供应链分析 | `query_suppliers` | `query_suppliers(category="compute_electronics")` |
| `/dfma` Step 3 替代供应商 | `query_suppliers` | `query_suppliers(keyword="SoC", tier="二线")` |
| structure_cmf 材料成本分解 | `query_materials` | `query_materials(bom_bucket="structure_cmf")` |
| 询问某类原料价格 | `query_materials` | `query_materials(keyword="HEPA")` |

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

### `/bom <品牌> <型号>`
> `/bom 石头 G30S Pro`

BOM 完整分析，核心命令。**只产出成本数据与供应链/风险信息，不给降本建议**。

Agent 执行 7 步流程：查已有数据 → 型号别名解析 → 补规格层 → 4-Stage 拆机 BOM（gen_teardown.py）→ 7 桶成本分析 → 供应链 & 风险提示 → 竞品差异对标。

输出：`data/teardowns/{slug}_{date}_teardown.csv` + 控制台报告（7 桶占比 · BOM/MSRP 比 · 偏差告警 · 技术亮点 · 供应商/专利风险）。

> **降本建议请使用 `/dfma`**——`/bom` 与 `/dfma` 职责分离：前者出"是什么成本"，后者出"该改什么、能省多少"。

### `/product <品牌> <型号>`
> `/product 追觅 X50 Ultra`

多源采集产品规格参数，录入数据库。**只做规格采集入库（含 FCC 链接），不做 BOM 分析**。

Agent 执行 6 步流程：查库 → 获取调研指令 → 多源检索（vacuumwars → 中关村 → 京东/天猫 → web_search）→ FCC 检索 → 汇总提取 30+ 字段 → 写入 `save_product`。

输出：产品摘要（10 项关键规格 + FCC 链接 + 完整度评分），存入 `products_db.json`。

> 要分析成本请用 `/bom`，要降本建议请用 `/dfma`。FCC 芯片识别后续用 `/fcc ocr`。

### `/fcc find <品牌> <型号>`
> `/fcc find 石头 G30S Pro`

在 fccid.io 匹配 FCC ID，列出全部文档的页面链接和 PDF 直链，写入 `links.json`。**不下载**，方便先在浏览器确认文档质量。

### `/fcc ocr <品牌> <型号>`
> `/fcc ocr 石头 G30S Pro`

读取 `links.json`（不存在时自动先 find），下载 Internal Photos / Parts List PDF，逐页视觉 OCR 识别芯片丝印，去重后写入 `latest.json` + 上游 CSV（`gen_teardown.py` Stage 0 自动读取）。

### `/cut <品牌> <型号>`
> `/cut 石头 G20S`

匹配 `components_lib.csv` 中 `tier=premium` 的件，给出替代方案 + 节省金额估算。

### `/dfma <品牌> <型号> [--segment <档位>]`
> `/dfma 卧安 K10+ Pro Combo`

DFMA 功能-成本矩阵分析。基于 7 桶 BOM 数据 × `user_value_weight` 计算每桶的**价值/成本比**，按象限分类（优先降本 / 溢价合理 / 保持投入 / 基准匹配），输出 `dfma_levers` 中的设计抓手清单 + 整机降本潜力估算。

`segment` 不传则按零售价/`market_segment` 自动推断（`entry` <¥2000，`mid` ¥2000-4000，`flagship` ≥¥4000）。

### `/vs <A> vs <B> [--bucket <桶>]`
> `/vs 科沃斯 X8 Pro vs 石头 S8 MaxV Ultra --bucket dock_station`

按指定桶的 `typical_items` 逐项对比；省略 `--bucket` 则整机 7 桶并排。

### `/find <关键词|桶>`
> `/find CPU`（或 `/find compute_electronics`）

遍历 `data/teardowns/*.csv`，按关键词或桶名抽取匹配条目。

### `/framework`
> `/framework`

运行 `export_framework_csv.py`，产出 `data/lib/bom_8bucket_framework.csv`（按需生成，不入库，填价对账用）。

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
