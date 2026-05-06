# unit-bot

**扫地机器人 BOM 成本分析平台** — 整机成本 4 级分解（5 大类 → 7 桶 → 功能模块 → 组件）· FCC 采集 · 降本优化

---

## 面向用户

| 用户 | 命令 | 用途 |
|------|------|------|
| **产品 / 成本团队** | `/bom 石头 G30S Pro` | 7 桶占比报告 + 供应链/风险提示 |
| **DFMA / 设计降本** | `/dfma 卧安 K10+` | 功能-成本矩阵 + DFMA 抓手 + 降本潜力 |
| **产品信息录入** | `/product 追觅 X50 Ultra` | 多源采集规格参数 + FCC 链接，录入产品库 |
| **拆机数据采集** | `/fcc find` + `/fcc ocr` | FCC 文档检索 + 视觉 OCR 识别 PCB 芯片丝印 |

辅助命令：`/cut` 溢价件识别 · `/vs` 子系统对标 · `/find` 数据库直查 · `/framework` 导出对账表，见[高级命令](#高级命令)。

### 安装

```bash
git clone https://github.com/fifteenbao/unit-bot
cd unit-bot
pip install -r requirements.txt
```

接入 OpenClaw（可选）：

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

### Quick Start

本地 CLI 先设置 API Key（三选一）：

```bash
export DEEPSEEK_API_KEY=sk-xxx    # 多轮 agent，客户端 DuckDuckGo 搜索
```

**`/product` — 采集规格，录入产品库**

```bash
/product 石头 G30S Pro
```

**`/fcc` — 采集 FCC 文档（可选，有数据时 Stage 0 优先使用）**

```bash
/fcc find 石头 G30S Pro                        # 查链接，不下载
/fcc ocr  石头 G30S Pro                        # 下载 PDF + OCR 识别芯片丝印

# 等价脚本
python scripts/fetch_fcc.py find "石头G30S Pro"
python scripts/fetch_fcc.py ocr  "石头G30S Pro"
```

**`/bom` — 7 桶成本分析 + 供应链/风险**

```bash
/bom 石头 G30S Pro

# 等价脚本
python scripts/gen_teardown.py "石头G30S Pro"
python scripts/gen_teardown.py "石头G30S Pro" --msrp 5999          # 指定零售价
python scripts/gen_teardown.py --csv data/teardowns/xxx.csv "xxx"  # 跳过 Stage 1，复用已有 CSV
```

**`/dfma` — 降本建议（在 `/bom` 之后跑）**

```bash
/dfma 石头 G30S Pro
```

---

## 核心能力

四个核心命令职责清晰、互不重叠——"录产品 / 出成本 / 出降本 / 采数据"。

### `/product` — 产品录入

6 步多源采集：查库 → 调研指令 → vacuumwars/中关村/电商/搜索 → FCC 检索 → 汇总提取 → 写入数据库。自动补全 30+ 规格字段 + 功能布尔值 + FCC 链接，录入后可直接跑 `/bom`。**只做规格采集，不做 BOM 分析。**

### `/bom` — BOM 成本分析

Stage 0 + 4-Stage 拆机 Pipeline，产出 7 桶 BOM 报告 + 整机全成本 + 供应链/风险提示。**只输出"是什么成本"，不给降本建议。**

Pipeline 按**整机成本 4 级分解结构**组织：

| 级别 | 内容 | 说明 |
|------|------|------|
| **一级·成本大类** | 硬件物料 / 人工+机器折旧 / 销售+管理费用 / 研发均摊 / 仓储物流售后 | 7 桶全部属于硬件物料；其余 4 类按档位固定参考值估算 |
| **二级·7 桶** | 算力与电子 / 感知系统 / 动力与驱动 / 清洁功能 / 基站系统 / 能源系统 / 整机结构CMF | BOM 硬件成本分析核心框架 |
| **三级·功能模块** | 每桶下的物理子系统（如导航系统、清洁系统、驱动系统等） | 按物理拆机组织 |
| **四级·组件** | 最小可计价单元，对应 BOM 单行（单颗芯片、单个电机、单张 PCB） | 拆机 CSV 每行 |

**一级成本占比参考**（来源：开源证券·科沃斯T80S拆解）：

| 大类 | 占零售价比例 | 说明 |
|------|------------|------|
| 硬件物料（7桶） | 40–55% | 唯一高度可变项，随功能配置显著变化；T80S实测约42.5% |
| 人工+机器折旧 | 6–12% | 组装/质检工时、设备折旧；T80S实测约7.5% |
| 销售+管理费用 | 20–35% | 渠道佣金+品牌推广+管理人员；T80S实测约25% |
| 研发均摊 | 3–8% | 算法版税/认证/样机；头部品牌靠规模摊薄；T80S实测约4.4% |
| 仓储物流售后 | 6–12% | 包材+物流+售后；T80S实测约7.5% |

**Pipeline 各阶段**：

| Stage | 职责 |
|-------|------|
| **0 FCC 上游** | 读 `fcc/{slug}/*_fcc_*.csv`，有则注入 Stage 1 prompt，无则跳过 |
| **1 Discovery** | 多源 web 调研，空结果自动降级为 framework_fill |
| **2 Enrichment** | SoC 识别 → 推导 PMIC/RAM/ROM 伴随件 |
| **~ Normalize** | LLM 自创桶名映射回 7 个合法 key |
| **3 Coverage Audit** | 对照 framework typical_items 审计 + 按产品特征过滤 + framework_fill 补缺 |
| **4 Aggregate & Bias** | 三级查价 + 辅料估算 + 7 桶偏差告警 + 一级成本结构输出 |

### `/dfma` — 设计降本

基于 7 桶框架的功能-成本矩阵分析。每桶携带 `user_value_weight`（入门/中档/旗舰三档价值权重）+ `dfma_levers`（设计抓手清单），按象限给出降本建议 + 整机潜力估算。**降本能力统一收口于此。**

| 象限 | 触发条件 | 行动 |
|------|---------|------|
| 优先降本 | 偏差 > +2pp 且价值权重 < 0.75 | 套用 dfma_levers |
| 溢价合理（需验证） | 偏差 > +2pp 且价值权重 ≥ 0.75 | 验证用户感知 |
| 保持投入 | 偏差 ≤ +2pp 且价值权重 ≥ 0.75 | 维持或追加 |
| 基准匹配 | 偏差 ≤ +2pp 且价值权重 < 0.75 | 不动 |

### `/fcc` — 数据采集

两步解耦：`find` 查文档链接（不下载，供人工确认质量）→ `ocr` 下载 PDF + 视觉识别 PCB 芯片丝印，产出可直通标准件库的上游 CSV。

---

## 数据库支撑

系统维护五类数据库，分层承担不同角色：

| # | 文件 | 角色（回答什么问题） | 维护方式 |
|---|------|------|---------|
| ① 产品规格库 | `data/products/products_db.json` | 这台机器**是什么** — MSRP / 规格 / 功能布尔值 | `save_product` 写入 · `import_products.py` 批量导入 |
| ② 拆机档案 | `data/teardowns/{slug}_{date}_teardown.csv` · `fcc/{slug}/*` | 这台机器**用了什么件** — 元器件级 BOM 清单 | `/fcc ocr` + `gen_teardown.py` 自动产出 |
| ③ 标准件库 | `data/lib/components_lib.csv` | 这类件**值多少钱** — 跨机型聚合的权威定价表 | `build_components.py` 汇总（仅接受 `fcc/teardown/confirmed`） |
| ④ 材料库 | `data/lib/materials.csv` | 原材料**怎么定价** — 22 种工程塑料/金属/滤材/织物原料单价区间 | 直接编辑 `price_min/price_max` 列 |
| ⑤ 供应商库 | `data/lib/suppliers.csv` | **谁在供货** — 37 家供应商的档次/地区/MOQ/账期 | 直接编辑 `tier/payment_terms/typical_parts` 列 |

**数据流向**：

```
①产品库（规格层）──┐
                   ├──→ /bom 7桶成本分析 ──→ /dfma 降本建议
②拆机档案 ─────────┤              ↑
   ↑                │         ③标准件库（查价）
   │                │         ④材料库（原材料单价）
/fcc ocr → fcc/*.csv ┘         ⑤供应商库（供应链标注）
   │
   └──→ build_components.py（白名单过滤）──→ ③标准件库
```

### 标准件库数据治理

`components_lib.csv` 只接受高置信度来源，`build_components.py` 汇总时按白名单过滤：

| confidence | 来源 | 入库 |
|-----------|------|------|
| `confirmed` | 人工/实物核实 | ✓ |
| `teardown` | 实物拆机 CSV | ✓ |
| `fcc` | FCC 文档 OCR 识别 | ✓ |
| `inferred` | Stage 2 启发式推导 | ✗ |
| `estimate` | 行业基准估算 | ✗ |
| `web` | 网络调研 | ✗ |

> FCC 数据可直通：跑完 `/fcc ocr` 后直接 `python scripts/build_components.py` 即可入库，无需先跑 gen_teardown。

### 数据维护入口

| 要修改什么 | 入口 |
|-----------|------|
| 桶定义 / 典型子项 / 占比基准 | `core/bom_8bucket_framework.json` |
| 一级成本参考值（人工/研发均摊等） | `core/bom_8bucket_framework.json` — `level1_categories` |
| 零件价格（日常） | `data/lib/components_lib.csv` — `cost_min/cost_max` 列 |
| 未收录件基准价 | `data/lib/standard_parts.json` |
| 原材料单价（ABS/铝合金/HEPA 等） | `data/lib/materials.csv` — `price_min/price_max` 列 |
| 供应商信息（档次/地区/采购条件） | `data/lib/suppliers.csv` — `tier/payment_terms/typical_parts` 列 |
| 型号别名 | `data/products/model_aliases.csv` |
| 新增竞品规格 | `data/products/products.csv` → `python scripts/import_products.py` |
| 标准件库入库 | `python scripts/build_components.py` |

### 项目结构

```
unit-bot/
├── SKILL.md                        # OpenClaw skill 元数据 + 命令文档
├── agent.py                        # Agent 主循环（Claude 工具调用）
├── config.yaml                     # 数据源路径配置（入 git）
│
├── core/                           # 运行时库
│   ├── bom_8bucket_framework.json  # ★ 7 桶标准模板（单一事实源）
│   ├── bucket_framework.py         # 框架加载器
│   ├── components_lib.py           # 标准件库 CRUD
│   ├── materials_lib.py            # 材料库 + 供应商库接入层
│   ├── model_aliases.py            # 型号别名匹配
│   ├── bom_rules.py                # 归桶规则 / 关键词匹配
│   ├── auxiliary_parts.py          # 辅料组装估算
│   ├── db.py                       # 产品数据库读写
│   ├── feishu_sync.py              # 飞书单向同步（可选）
│   └── config.py                   # config.yaml 加载
│
├── scripts/                        # 离线维护脚本
│   ├── gen_teardown.py             # 拆机 4-Stage Pipeline
│   ├── fetch_fcc.py                # FCC 采集（find + ocr）
│   ├── import_products.py          # 产品库导入
│   ├── build_components.py         # teardown/FCC CSV → components_lib.csv
│   ├── update_prices.py            # 动态爬价
│   ├── export_framework_csv.py     # 7 桶对账 CSV（按需）
│   └── start.py                    # Agent 启动入口
│
└── data/                           # 数据目录（大部分私有，不入 git）
    ├── lib/
    │   ├── components_lib.csv      # 权威查价表（标准件，200+ SKU）
    │   ├── standard_parts.json     # SoC 参考 / 伴随件 heuristics
    │   ├── materials.csv           # ★ 原材料单价库（22 种）
    │   └── suppliers.csv           # ★ 供应商库（37 家）
    ├── products/
    │   ├── model_aliases.csv       # ★ 入 git
    │   ├── products.csv            # 私有
    │   └── products_db.json        # 私有，运行时缓存
    └── teardowns/
        ├── {slug}_{YYYYMMDD}_teardown.csv
        └── fcc/{slug}/
            ├── links.json          # find 产出
            ├── latest.json         # ocr 产出
            ├── {slug}_fcc_{date}.csv
            └── pdfs/
```

---

## 高级命令

### `/cut <品牌> <型号>`

匹配 `components_lib.csv` 中 `tier=premium` 的件，给出替代方案 + 节省金额估算。与 `/dfma` 互补：`/cut` 是**件级**单点降本，`/dfma` 是**整机系统级**降本。

### `/vs <A> vs <B> [--bucket <桶>]`

子系统或整机对标。省略 `--bucket` 则 7 桶并排，带 `--bucket` 则按该桶 `typical_items` 逐项对比。

```
/vs 科沃斯 X8 Pro vs 石头 S8 MaxV Ultra --bucket dock_station
```

### `/find <关键词|桶>`

遍历 `data/teardowns/*.csv`，按关键词或桶名抽取匹配条目。

```
/find RK3588S
/find compute_electronics
```

### `/framework`

导出 7 桶对账 CSV，产出 `data/lib/bom_8bucket_framework.csv`，用于填价对账（按需，不入 git）。

---

## 配置

### 环境变量（本地 CLI）

优先级：AIHUBMIX > DeepSeek > Anthropic，三选一即可。

| 变量 | 说明 |
|------|------|
| `AIHUBMIX_API_KEY` | 优先级最高，带服务端 web_search |
| `DEEPSEEK_API_KEY` | 次优先，客户端 DuckDuckGo 搜索 + httpx 抓取 |
| `ANTHROPIC_API_KEY` | 兜底，需能直连 Anthropic API |

### `config.yaml` 数据源路径

| 域 | 默认路径 |
|---|---|
| 产品数据库 | `data/products/products_db.json` |
| 拆机数据 | `data/teardowns/{slug}_{YYYYMMDD}_teardown.csv` |
| FCC 上游 | `data/teardowns/fcc/{slug}/{slug}_fcc_{date}.csv` |
| 标准件库 | `data/lib/components_lib.csv` |
| 基准价库 | `data/lib/standard_parts.json` |
| 材料库 | `data/lib/materials.csv` |
| 供应商库 | `data/lib/suppliers.csv` |
| 型号映射 | `data/products/model_aliases.csv` |
| 7 桶框架 | `core/bom_8bucket_framework.json` |

飞书同步（可选展示层，未配置时静默跳过）：

```yaml
feishu:
  product_obj_token: ""
  teardown_obj_token: ""
  components_obj_token: ""
```

---

## 参考资料

- [fccid.io](https://fccid.io) — FCC 申请文档检索
- [fcc.report](https://fcc.report) — FCC 文档 PDF 直链
- [立创商城](https://www.szlcsc.com) · [Digi-Key](https://www.digikey.cn) · [1688](https://www.1688.com) — 动态价格来源
- [`SKILL.md`](SKILL.md) — OpenClaw skill 完整文档（Pipeline 细节 / 置信度层级 / 7 桶框架字段说明）
- 开源证券·科沃斯T80S成本拆解（2024）— 一级成本占比参考来源
