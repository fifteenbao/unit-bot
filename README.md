# unit-bot

**扫地机器人 BOM 成本分析平台** — 竞品拆机 · 7 桶成本核算 · FCC 采集 · 降本优化

- 数据：`data/` 目录私有，框架模板和型号映射公开入 git

---

## 面向用户

| 用户 | 核心命令 | 用途 |
|------|---------|------|
| **产品 / 成本团队** | `/bom 石头 G30S Pro` | 7 桶占比报告 + 供应链/风险提示（"是什么成本"） |
| **DFMA / 设计降本** | `/dfma 卧安 K10+` | 功能-成本矩阵 + DFMA 抓手 + 降本潜力（"该改什么、能省多少"） |
| **产品信息录入** | `/product 追觅 X50 Ultra` | 多源采集规格参数 + FCC 链接，录入产品库 |
| **拆机数据采集** | `/fcc find` + `/fcc ocr` | FCC 文档检索 + 视觉 OCR 识别 PCB 芯片丝印 |
| **数据维护** | 见下方"数据分类"章节 | 维护三类数据库（产品库 / 拆机档案 / 标准件库） |

> 其他辅助命令（`/cut` 溢价件识别、`/vs` 子系统对标、`/find` 数据库直查、`/framework` 导出对账表）见[高级命令](#高级命令)。

---

## 核心能力

围绕四个核心命令构建，"录产品 / 出成本 / 出降本 / 采数据"职责清晰、互不重叠：

- **`/product` 产品录入**：6 步多源采集（查库 → 调研指令 → vacuumwars/中关村/电商/搜索 → FCC 检索 → 汇总提取 → 写入数据库），自动补全 30+ 规格字段 + 功能布尔值 + FCC 链接。**录入后可直接跑 `/bom` 分析成本**。
- **`/bom` 成本分析**：Stage 0 + 4-Stage 拆机 Pipeline（FCC 上游 → web 调研 → SoC 伴随件推导 → 覆盖率审计 + 产品特征检测 + 框架补缺写入 CSV → 三级查价 + 辅料组装 + 一级成本估算），按 4 级成本结构组织，产出 7 桶 BOM 报告 + 整机全成本 + 供应链/风险提示。**只输出"是什么成本"**。
- **`/dfma` 设计降本**：基于 7 桶框架的功能-成本矩阵分析，每桶携带 `user_value_weight`（入门/中档/旗舰三档价值权重）+ `dfma_levers`（设计抓手清单），按象限给出降本建议 + 整机潜力估算。**降本能力统一收口于此**。
- **`/fcc` 数据采集**：两步解耦——`find` 查文档链接（不下载，先供人工确认质量）→ `ocr` 下载 PDF + 视觉识别 PCB 芯片丝印，产出可直通标准件库的上游 CSV。

**底层支撑**：
- **7 桶框架单一事实源**：`bom_8bucket_framework.json` 改一处，gen_teardown / dfma / export_csv 自动同步。
- **标准件库白名单**：200+ SKU，三层定价（权威 → fallback → 桶兜底）；入库仅接受 `fcc / teardown / confirmed` 三档置信度，拒绝 `inferred / estimate / web` 推测来源污染。
- **型号别名匹配**：国内/海外型号自动映射，支持模糊搜索。

---

## 安装

```bash
git clone https://github.com/fifteenbao/unit-bot
cd unit-bot
pip install -r requirements.txt
```

验证安装：

```bash
python scripts/gen_teardown.py --help
python scripts/fetch_fcc.py --help
```

接入 OpenClaw（可选）：

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

---

## Quick Start

### 路径 A · Agent 命令（接入 OpenClaw 后）

```
/bom 石头 G30S Pro          # 成本数据 + 供应链/风险
/dfma 石头 G30S Pro          # 在 /bom 之后跑，输出降本建议
```

Agent 自动完成：查规格 → 爬元器件 → 7 桶成本 → 供应链/风险 → 竞品对比。输出拆机 CSV + 控制台报告。
降本方案不在 `/bom` 输出，统一通过 `/dfma` 命令获取。

### 路径 B · 本地 CLI

先设置 LLM API Key（三选一）：

```bash
export AIHUBMIX_API_KEY=sk-xxx    # 推荐，有 web_search
export DEEPSEEK_API_KEY=sk-xxx    # 便宜，无 web_search
export ANTHROPIC_API_KEY=sk-xxx   # 原生
```

然后运行：

```bash
# 1. 采集 FCC 文档（可选，有 FCC 数据时 Stage 0 优先使用）
python scripts/fetch_fcc.py find "石头G30S Pro"
python scripts/fetch_fcc.py ocr  "石头G30S Pro"

# 2. 生成拆机 BOM（4-Stage）
python scripts/gen_teardown.py "石头G30S Pro"

# 3. 更新标准件库价格（可选）
python scripts/update_prices.py --dry-run
python scripts/update_prices.py

# 调试技巧
python scripts/gen_teardown.py --csv data/teardowns/xxx_teardown.csv "xxx"   # 跳过 Stage 1，复用已有 CSV
python scripts/gen_teardown.py --msrp 2999 "xxx"                              # 指定 MSRP，跳过自动查询
```

---

## 命令参考

### `/bom <品牌> <型号>`

BOM 完整分析，核心命令。**只产出成本数据与供应链/风险信息，不给降本建议**。

```
/bom 石头 G30S Pro
/bom 追觅 X40 Ultra
```

Agent 执行 7 步流程：查已有数据 → 型号别名解析 → 补规格层 → 4-Stage 拆机 BOM → 7 桶成本分析 → 供应链 & 风险提示 → 竞品差异对标。

输出：
- `data/teardowns/{slug}_{date}_teardown.csv`
- 控制台：7 桶占比 · BOM/MSRP 比 · 偏差告警 · 技术亮点 · 供应商/专利风险

> **降本建议请使用 `/dfma`**——`/bom` 与 `/dfma` 职责分离：前者出"是什么成本"，后者出"该改什么、能省多少"。

---

### `/product <品牌> <型号>`

多源采集产品规格参数，录入产品数据库。**只做规格采集入库（含 FCC 链接），不做 BOM 分析**。

```
/product 追觅 X50 Ultra
/product 石头 G30S Pro
```

Agent 执行 6 步流程：查库 → 获取调研指令 → 多源检索（vacuumwars → 中关村在线 → 京东/天猫 → web_search）→ FCC 检索 → 汇总提取 30+ 字段 → 写入 `save_product`。

输出：
- 产品摘要（10 项关键规格 + FCC 链接 + 完整度评分）
- 写入 `data/products/products_db.json`

> 要分析成本请用 `/bom`，要降本建议请用 `/dfma`。FCC 芯片识别后续用 `/fcc ocr`。

---

### `/fcc find <品牌> <型号>`

查找 FCC 文档链接，不下载，供人工确认文档质量。

```
/fcc find 石头 G30S Pro
/fcc find 科沃斯 X8 Pro --fcc-id 2A6HE-DEX8PRO   # 直接指定 FCC ID
/fcc find 石头 G30S Pro --force                    # 忽略缓存重新查找
```

输出 `data/teardowns/fcc/{slug}/links.json`，并打印 fccid.io / fcc.report 页面链接，可在浏览器手动核查。

支持品牌：石头 · 追觅 · 科沃斯 · 云鲸 · 卧安 · 杉川 · 安克(Eufy) · 小米 · iRobot

---

### `/fcc ocr <品牌> <型号>`

下载 PDF + 视觉 OCR 识别 PCB 芯片丝印。读取 `links.json`，不存在时自动先执行 find。

```
/fcc ocr 石头 G30S Pro
/fcc ocr 石头 G30S Pro --force   # 忽略缓存重跑
```

输出：
- `data/teardowns/fcc/{slug}/latest.json`（OCR 原始结果）
- `data/teardowns/fcc/{slug}/{slug}_fcc_{date}.csv`（上游 CSV，`gen_teardown.py` Stage 0 自动读取）

> 两步解耦的意义：FCC 图片质量良莠不齐，先 `find` 让人工确认文档内容，再决定是否消耗 API 做 OCR。

---

### `/dfma <品牌> <型号> [--segment <档位>]`

DFMA 功能-成本矩阵分析。基于 7 桶 BOM 数据 × `user_value_weight` 计算每桶的**价值/成本比**，按象限给出设计抓手建议。

```
/dfma 卧安 K10+ Pro Combo
/dfma 石头 G30S Pro --segment flagship   # 显式指定档位
```

**输入要求**：产品已有 `bom_cost` 各桶数据（先跑 `/bom` 或 `generate_bom_estimate`）。

**输出**：
- 7 桶矩阵：成本占比 · 偏差 · 用户价值权重 · 价值成本比 · 象限分类
- 优先降本桶清单（高成本低价值）
- 每桶的 DFMA 抓手（来自 `dfma_levers` 字段）
- 整机降本潜力估算（元/台）

**象限规则**：

| 象限 | 触发条件 | 行动建议 |
|------|---------|---------|
| 优先降本 | 偏差 > +2pp 且 价值权重 < 0.75 | 直接套用 dfma_levers 降本 |
| 溢价合理（需验证） | 偏差 > +2pp 且 价值权重 ≥ 0.75 | 验证用户感知，必要时降本 |
| 保持投入 | 偏差 ≤ +2pp 且 价值权重 ≥ 0.75 | 维持或追加（差异化卖点） |
| 基准匹配 | 偏差 ≤ +2pp 且 价值权重 < 0.75 | 不动 |

**价值成本比**：`< 0.8` 优先降本，`> 1.2` 可追加投入。

---

## 数据分类

系统维护三类数据库，承担不同的角色：

| 数据库 | 文件路径 | 角色 | 来源 | 维护方式 |
|--------|---------|------|------|---------|
| **① 产品规格库** | `data/products/products.csv` · `products_db.json` | 描述"这台机器**是什么**" — MSRP / 规格 / 功能布尔值 | 官网 / 评测 / `web_search` | `import_products.py` 导入 · `save_product` 写入 |
| **② 拆机档案** | `data/teardowns/{slug}_{date}_teardown.csv` · `data/teardowns/fcc/{slug}/*` | 描述"这台机器**用了什么件**" — 元器件级 BOM 清单 | `/fcc find/ocr` + `gen_teardown.py` 4-Stage Pipeline | 自动产出，按机型一份 CSV |
| **③ 标准件库** | `data/lib/components_lib.csv` | 描述"这类件**值多少钱**" — 跨机型聚合的权威定价表 | `build_components.py` 汇总（白名单过滤） | 仅接受 `fcc / teardown / confirmed` 三档置信度 |

**数据流向**：

```
①产品库（规格层）        ──┐
                          ├─→  /bom 7 桶成本分析  ──→  /dfma 降本建议
②拆机档案（实物 BOM）  ──┤                          ↑
   ↑                      │                      ③标准件库（查价）
   │                      │
/fcc ocr → fcc/*.csv ─────┘
   │
   └─→ build_components.py (白名单过滤) ─→ ③标准件库
```

**职责边界**：
- **①** 是产品的"身份证"：规格、价格、功能开关，不含 BOM 成本。
- **②** 是单台机器的"X 光片"：每个零件的型号、归桶、来源 URL。
- **③** 是行业的"价格地图"：从 ② 中按"件"维度聚合，附加供应商/替代方案/专利风险。

> 详细的入库治理规则（confidence 白名单）见 [标准件库数据治理](#标准件库数据治理)。

---

## 高级命令

不常用，但偶尔需要。

### `/cut <品牌> <型号>`

降本机会识别，匹配 `components_lib.csv` 中 `tier=premium` 的件。

```
/cut 石头 G20S
```

输出：溢价件列表 · 替代方案 · 节省金额估算 · 替换风险提示。

> 与 `/dfma` 的区别：`/cut` 是**单点件级**降本（针对某个标记为 `premium` 的标准件），`/dfma` 是**整机系统级**降本（按桶+用户价值权重），两者互补。

---

### `/vs <A> vs <B> [--bucket <桶>]`

子系统或整机对标。

```
/vs 石头P10pro vs 科沃斯X2pro
/vs 科沃斯 X8 Pro vs 石头 S8 MaxV Ultra --bucket dock_station
```

不带 `--bucket` 则整机 7 桶并排。带 `--bucket` 则按该桶的 `typical_items` 逐项对比。

---

### `/find <关键词|桶>`

数据库直查，遍历 `data/teardowns/*.csv`。

```
/find SoC
/find compute_electronics
/find RK3588S
```

---

### `/framework`

按需导出 7 桶对账 CSV，不入 git，用于填价对账。

```
/framework
```

产出：`data/lib/bom_8bucket_framework.csv`

---

## 环境变量（仅本地 CLI 需要，Agent/OpenClaw 路径不需要）

三选一即可，优先级：AIHUBMIX > DeepSeek > Anthropic。

| 变量 | 说明 |
|------|------|
| `AIHUBMIX_API_KEY` | 优先级最高，带服务端 web_search |
| `DEEPSEEK_API_KEY` | 次优先，便宜但无 web_search |
| `ANTHROPIC_API_KEY` | 兜底，需能直连 Anthropic API |

---

## 数据源配置（`config.yaml`）

所有文件路径集中在根目录 `config.yaml`，修改后立即生效，无需重启。

| 域 | 默认路径 | 说明 |
|---|---|---|
| 产品数据库 | `data/products/products_db.json` | MSRP / 规格 / 功能 |
| 拆机数据 | `data/teardowns/{slug}_{YYYYMMDD}_teardown.csv` | `gen_teardown.py` 产出 |
| FCC 上游 | `data/teardowns/fcc/{slug}/{slug}_fcc_{date}.csv` | `fetch_fcc.py ocr` 产出 |
| 标准件库 | `data/lib/components_lib.csv` | 权威定价（人工维护） |
| 基准价库 | `data/lib/standard_parts.json` | SoC 参考表 / 伴随件 heuristics |
| 型号映射 | `data/products/model_aliases.csv` | 国内/海外别名（入 git） |
| 7 桶框架 | `core/bom_8bucket_framework.json` | 单一事实源 |

飞书同步（可选）：

```yaml
feishu:
  product_obj_token: ""
  teardown_obj_token: ""
  components_obj_token: ""
```

> `obj_token` 即多维表格的 `app_token`。`config.yaml` 已在 `.gitignore` 内，secrets 走环境变量。

---

## 开发与维护

### 项目结构

```
unit-bot/
├── SKILL.md                    # OpenClaw skill 元数据 + 命令文档
├── agent.py                    # Agent 主循环（Claude 工具调用）
├── config.yaml                 # 数据源路径配置（入 git）
│
├── core/                       # 运行时库
│   ├── bucket_framework.py     # 7 桶框架加载器
│   ├── bom_8bucket_framework.json  # ★ 7 桶标准模板（单一事实源）
│   ├── components_lib.py       # 标准件库 CRUD
│   ├── model_aliases.py        # 型号别名匹配
│   ├── bom_rules.py            # 归桶规则 / 关键词匹配
│   ├── db.py                   # 产品数据库读写
│   ├── feishu_sync.py          # 飞书单向同步
│   └── config.py               # config.yaml 加载
│
├── scripts/                    # 离线维护脚本
│   ├── gen_teardown.py         # 拆机 4-Stage Pipeline
│   ├── fetch_fcc.py            # FCC 采集（find + ocr）
│   ├── import_products.py      # 产品库导入
│   ├── build_components.py     # 拆机 / FCC CSV → components_lib.csv（白名单过滤，仅接受 fcc/teardown/confirmed）
│   ├── update_prices.py        # 动态爬价
│   ├── export_framework_csv.py # 7 桶对账 CSV（按需）
│   └── start.py                # Agent 启动入口
│
├── web/                        # Web UI（Next.js + FastAPI，见下方）
│
└── data/                       # 数据目录（大部分私有，不入 git）
    ├── lib/
    │   ├── components_lib.csv          # 权威查价表
    │   └── standard_parts.json         # SoC 参考 / 伴随件 heuristics
    ├── products/
    │   ├── model_aliases.csv           # ★ 入 git
    │   ├── products.csv                # 私有
    │   └── products_db.json            # 私有，运行时缓存
    └── teardowns/
        ├── {slug}_{YYYYMMDD}_teardown.csv
        └── fcc/{slug}/
            ├── links.json              # find 产出
            ├── latest.json             # ocr 产出
            ├── {slug}_fcc_{date}.csv   # gen_teardown Stage 0 上游
            └── pdfs/
```

### 数据维护

| 需要修改 | 入口文件 |
|---------|---------|
| 桶定义 / 典型子项 / 占比基准 | `core/bom_8bucket_framework.json` |
| 零件价格（日常） | `data/lib/components_lib.csv` — `cost_min` / `cost_max` 列 |
| 未收录件基准价 | `data/lib/standard_parts.json` |
| 型号别名 | `data/products/model_aliases.csv` |
| 新增竞品规格 | `data/products/products.csv` → `python scripts/import_products.py` |
| 标准件库入库 | `python scripts/build_components.py`（汇总 teardowns + FCC CSV，仅接受 `fcc/teardown/confirmed` 三档置信度） |

#### 标准件库数据治理

`components_lib.csv` 是**权威数据**，只接受高置信度来源。`build_components.py` 在汇总时按白名单过滤：

| 置信度 | 来源 | 是否入库 |
|--------|------|---------|
| `confirmed` | 人工/实物核实 | ✓ |
| `teardown` | 实物拆机 CSV | ✓ |
| `fcc` | FCC 文档 OCR 识别 | ✓ |
| `inferred` | Stage 2 启发式推导 | ✗ 过滤 |
| `estimate` | 行业基准估算 | ✗ 过滤 |
| `web` | 网络调研 | ✗ 过滤 |

> **FCC 数据可直通**：跑完 `/fcc ocr` 后无需先经 `gen_teardown`，直接 `python scripts/build_components.py` 即可入库。
> 选择性入库时可指定路径：`python scripts/build_components.py data/teardowns/fcc/石头G30SPro/`

### 常用调试命令

```bash
# 跳过爬虫，复用已有 CSV 调试 Stage 2-4
python scripts/gen_teardown.py --csv data/teardowns/卧安K10+_20260422_teardown.csv "卧安K10+"

# 动态爬价演习（不写入）
python scripts/update_prices.py --bucket compute_electronics --dry-run

# 导出 7 桶对账表
python scripts/export_framework_csv.py
```

---

## 参考资料

- [fccid.io](https://fccid.io) — FCC 申请文档检索
- [fcc.report](https://fcc.report) — FCC 文档 PDF 直链
- [立创商城](https://www.szlcsc.com) · [Digi-Key](https://www.digikey.cn) · [1688](https://www.1688.com) — 动态价格来源
- [`SKILL.md`](SKILL.md) — OpenClaw skill 完整文档（Pipeline 细节 / 置信度层级 / 7 桶框架字段说明）

---

## 当前进度（2026-04）

### ✅ 已完成

- **7 桶框架定型**：7 类成本桶 + 入门/中档/旗舰三档基准占比，单一事实源。
- **标准件库**：200+ SKU，三层定价，动态爬价框架。
- **FCC 两步工作流**：`find`（查链接）+ `ocr`（识别），两步解耦支持人工干预。
- **型号别名匹配**：国内/海外型号自动映射，支持模糊搜索。
- **飞书单向同步**：分析结果推送到多维表格，未配置时静默跳过。
- **首个 BOM 样例打通**：938 行原始 BOM → 416 计价单元，5/7 桶占比落在 ±5% 基准区间。

### 🚧 进行中

- FCC OCR 元器件自动归类（视觉模型识别 PCB 芯片丝印）
- Web UI（PaddleOCR 本地识别 + 数据库浏览界面）
- 动态价格爬取稳定化（立创 / Digi-Key / 1688 数据源）

### 📋 待办

- 成本差异可视化（桶级柱状图、机型并排 diff）
- 降本建议引擎（溢价件识别、替代方案、节省金额估算）
- 更多品牌 / 海外市场型号别名覆盖
