# unit-bot — 扫地机器人 行业情报 & BOM 成本分析平台

内部工具平台，面向产品 / 成本 / 研发团队，提供扫地机器人 (RVC) 品类的**市场调研**、**竞品拆机分析**、**BOM 成本差异计算**、**降本优化建议**能力。

> 支持作为 **OpenClaw skill** 接入飞书 / Slack / Telegram 等频道，也可直接以 CLI / Web UI 方式使用。

---

## 平台能力（四大模块）

| 模块 | 目的 | 数据载体 | 关键脚本 |
|------|------|---------|---------|
| **① 市场调研** | 竞品规格、价位、配置横向对比 | `data/products/` | `import_products.py` |
| **② 竞品拆机** | 主要元器件型号、供应商识别（人工拍照 / FCC / 拆机报告） | `data/teardowns/` | `gen_teardown.py`、`fetch_fcc.py` |
| **③ 标准件库** | 价格权威来源、8桶分类维护、动态爬价 | `data/lib/components_lib.csv` | `build_components.py`、`update_prices.py` |
| **④ BOM 成本分析** | 自家 BOM 8桶占比、降本空间 | `data/bom/`（私有，不入 git） | 项目内专用脚本 |

---

## 当前进度（2026-04）

### ✅ 已完成

- **8 桶框架定型**：`SKILL.md` 定义 8 类成本桶 + 入门/中档/旗舰三档基准占比。
- **标准件库初具规模**：200+ SKU，覆盖多款竞品（云鲸 / 石头 / 科沃斯 / 追觅 / 卧安）。
- **三层定价机制**：`components_lib.csv`（权威）→ `standard_parts.json`（通用 fallback）→ 桶兜底。
- **聚合机制**：规则标 `(聚合)` 的装配类零件按整机 1 份计入，避免父子件重复计价。
- **飞书单向同步**：写入本地后推送到飞书多维表格（不回读，未配置时跳过）。
- **首个 BOM 标准样例打通**：单款机型 938 行原始 BOM → 416 个计价单元，8 桶占比 5/8 落在 ±5% 基准区间内（内部项目，样例数据不入 git）。

### 🚧 进行中

- FCC / 拆机照片 **OCR + 元器件自动归类**（当前 `fetch_fcc.py` 仅抓 PDF，视觉识别待接入）。
- **Web UI**：OCR 识别上传、数据库浏览与检索（见下方"前端" 章节）。
- **动态价格爬取**：`update_prices.py` 已有框架，数据源（立创 / Digi-Key / 1688）接入稳定性优化中。

### 📋 待办

- 成本差异可视化（桶级柱状图、机型并排 diff）。
- 降本建议引擎（溢价件识别、替代方案推荐、节省金额估算）。
- 型号别名模糊匹配覆盖更多品牌与海外市场。

---

## 项目结构

```
unit-bot/
├── SKILL.md                    # OpenClaw skill 元数据 + 8 桶规范定义
├── agent.py                    # Agent 主循环（Claude 工具调用）
│
├── core/                       # 运行时库
│   ├── config.py               # config.yaml 加载
│   ├── db.py                   # 产品数据库读写
│   ├── bom_loader.py           # 拆机数据只读
│   ├── bom_rules.py            # BOM 归桶规则 / 关键词匹配
│   ├── components_lib.py       # 标准件库 CRUD（消费 data/lib/components_lib.csv）
│   ├── model_aliases.py        # 国内/海外型号别名匹配
│   ├── feishu_sync.py          # 飞书单向同步
│   ├── bucket_framework.py     # ★ 8 桶框架加载器（prompt 渲染 / 覆盖审计）
│   └── bom_8bucket_framework.json  # ★ 8 桶标准模板（单一事实源，公开）
│
├── scripts/                    # 离线维护工具（公开）
│   ├── import_products.py      # ① 产品库导入：products.csv → products_db.json
│   ├── gen_teardown.py         # ② 拆机 4-Stage Pipeline（消费 core/bucket_framework）
│   ├── fetch_fcc.py            # ② FCC 照片 / PDF 抓取（OCR 待接入）
│   ├── build_components.py     # ③ 拆机 CSV → data/lib/components_lib.csv（不覆盖人工价格）
│   ├── update_prices.py        # ③ 动态爬价 → 更新 components_lib + price_history
│   ├── export_framework_csv.py # ★ JSON 模板 → data/lib/*.csv（对账工作表）
│   ├── migrate_lib_price_tier.py  # 价格分层字段迁移工具
│   └── start.py                # Agent 启动入口
│
├── web/                        # 前端 Web UI（Next.js + FastAPI，见下方章节）
│   ├── api/                    # FastAPI 后端（数据查询 / OCR 识别代理）
│   └── ui/                     # Next.js 前端（仪表盘 / OCR / 数据浏览）
│
├── data/                       # 内容私有（仅 data/products/model_aliases.json 入 git）
│   │                             上游/下游关系由 config.yaml 声明
│   ├── lib/                    # 标准件库（★ 核心配置）
│   │   ├── components_lib.csv              # ★ 权威查价表（SKU 级，人工维护 — 无更上游）
│   │   └── standard_parts.json             # ★ 重要价格参考源：SoC 参考表 / 伴随件 heuristics
│   │                                         # ↑ 上游: components_lib.csv（人工同步）
│   ├── products/               # 产品元数据
│   │   ├── products.csv                    # 市场调研原始表（私有，人工维护 — 无更上游）
│   │   ├── products_db.json                # 产品主数据库（私有）  ↑ 上游: products.csv（import_products.py）
│   │   └── model_aliases.json              # 公开：国内/海外型号映射（人工维护 — 无更上游）
│   ├── teardowns/              # 竞品拆机
│   │   ├── {机型}_{YYYYMMDD}_teardown.csv  # 下游合并产出         ↑ 上游: fcc/{slug}/*_fcc_*.csv (FCC) + web_search
│   │   └── fcc/{slug}/                     # FCC 档案区
│   │       ├── latest.json                 # OCR 原始结果
│   │       └── {slug}_fcc_{YYYYMMDD}.csv   # 上游 CSV（喂给 gen_teardown）  ↑ 上游: latest.json（OCR）
│   └── bom/                    # 自家 BOM（私有项目数据，如 C33 成本评估表）
│
├── config.yaml                 # ★ 数据源路径配置（入 git，声明所有上下游文件位置）
└── requirements.txt
```

> 上游/下游 → 以 `config.yaml` 为单一事实源声明。飞书 `APP_ID` / `APP_SECRET` 等 secrets 走环境变量，不进 config.yaml。

---

 

对账 CSV 是 JSON 模板的**单向衍生品**，不入 git。做竞品对比时跑一次 `python scripts/export_framework_csv.py` 即可生成最新版本。gen_teardown 和 analyze 直接读 JSON，无需 CSV。

---

## 数据流总览

```
① 市场调研
   人工维护 products.csv
     └─→ import_products.py ─→ products_db.json
                                    ↕  Agent 读写 / 飞书推送

② 竞品拆机
   机型名
     └─→ gen_teardown.py (4-Stage, 对齐 core/bom_8bucket_framework.json)
           Stage 1 Discovery   爬 MyFixGuide/知乎/FCC  → 元器件型号 + confidence
                               （prompt 从 framework 动态渲染桶清单）
           Stage 2 Enrichment  SoC heuristic → 伴随件（PMIC/RAM/ROM）
           Stage 3 Coverage    对照 framework typical_items → 报缺失关键子项
           Stage 4 Aggregate   三级查价 (components_lib → standard_parts → 兜底)
                               按桶汇总 + ±5% 占比偏差告警 + BOM/MSRP 比
     └─→ fetch_fcc.py         FCC 图/PDF 抓取
                              [🚧 OCR 识别待接入 → 自动归类到 8 桶]
     └─→ data/teardowns/{机型}_teardown.csv（人工核准后）
          └─→ build_components.py ─→ components_lib.csv（聚合更新）

③ 标准件库
   update_prices.py  ← web 爬虫 (立创/Digi-Key/1688)
     └─→ components_lib.csv   (更新 cost_min/cost_max)
     └─→ price_history.csv    (变动审计)
   standard_parts.json        ← 未收录件人工 fallback

④ 自家 BOM 成本分析（内部项目，不公开）
   原始 BOM.csv
     └─→ 首次：播种标准件入库
     └─→ 分析脚本：层级解析 + 规则分类 + 三层定价 + 聚合
          └─→ 8 桶占比报告 + per-leaf 明细 CSV
```

置信度层级：`database`（人工）> `teardown`（拆机识别）> `fcc`（照片 OCR）> `web`（调研）> `inferred`（同平台推断）> `estimate`（基准）

---

## 8 桶框架工作流闭环

`core/bom_8bucket_framework.json` 是**单一事实源**——桶定义、典型子项、example_spec、行业占比基准、归桶边界、容差规则，全部在这里。所有消费方通过 `core/bucket_framework.py` 读取，模板更新一处、下游四处自动同步：

```
core/bom_8bucket_framework.json  ← 单一事实源（通用模板，无敏感数据）
  ├─ buckets.*.definition              → Stage 1 prompt
  ├─ buckets.*.typical_items           → Stage 1 prompt + Stage 3 审计
  ├─ buckets.*.boundary_notes          → Stage 1 prompt（全量）
  ├─ buckets.*.industry_pct_range/avg  → Stage 4 基准 + 合格区间
  └─ validation_rules.*                → Stage 4 容差 + BOM/MSRP 期望
          │
          ▼
core/bucket_framework.py         ← 加载器 API
          │
          ├─→ scripts/gen_teardown.py
          │        ├─ Stage 1 prompt 注入（定义 + typical_items + boundary_notes 全量）
          │        ├─ Stage 2.5 桶名归一化（LLM 自创命名兜底映射到 bucket_keys()）
          │        ├─ Stage 3 覆盖审计（对照 typical_items 报缺失关键子项）
          │        └─ Stage 4 占比基准（± bucket_pct_tolerance 偏差 + BOM/MSRP 诊断）
          │
          ├─→ scripts/analyze_*.py             （成本分桶 / 占比基准校验）
          │
          └─→ scripts/export_framework_csv.py  （按需生成，不入库）
                   └─→ data/lib/bom_8bucket_framework.csv（人看对账表，填价用）
```

对账 CSV 是 JSON 模板的**单向衍生品**，不入 git。做竞品对比时跑一次 `python scripts/export_framework_csv.py` 即可生成最新版本。gen_teardown 和 analyze 直接读 JSON，无需 CSV。

---

## 数据库配置（`config.yaml`）

所有数据路径集中在根目录 [`config.yaml`](config.yaml)，便于 Skill / 脚本统一定位。编辑后立即生效，无需重启。

| 分区 | 字段 | 默认路径 | 说明 |
|------|------|---------|------|
| `products` | `csv` | `data/products/products.csv` | 人工维护输入源 |
|   | `db_json` | `data/products/products_db.json` | 运行时缓存 |
|   | `fields_required` | 见 yaml | 导入时必填列 |
| `teardown` | `dir` | `data/teardowns` | 每机型一份 `{slug}_teardown.csv` |
|   | `fcc_dir` | `data/teardowns/fcc` | FCC 采集结果（独立） |
| `components` | `lib_csv` | `data/lib/components_lib.csv` | 标准件权威价 |
|   | `standard_parts_json` | `data/lib/standard_parts.json` | 未收录件 fallback |
|   | `model_aliases_json` | `data/products/model_aliases.json` | 国内/海外型号映射 |
| `framework` | `json` | `core/bom_8bucket_framework.json` | 8 桶单一事实源 |
|   | `loader` | `core.bucket_framework` | Python 加载器模块路径 |
| `feishu` | `*_obj_token` | (空) | 可选展示层只写同步 |

> 未配置的 feishu 字段自动静默跳过；本地文件路径支持自定义，Agent 和所有脚本通过相同配置定位数据。

---

## 8 桶 BOM 成本分析框架

| # | 子系统 | 核心内容 | 入门机 | 中档机 | 旗舰机 |
|---|--------|---------|:-----:|:-----:|:-----:|
| 1 | **算力与电子** | SoC · Wi-Fi/BT · 被动元件 | ~13% | ~12% | ~11% |
| 2 | **感知系统** | LDS/dToF · 摄像头 · IMU · 超声波 | ~8% | ~10% | ~11% |
| 3 | **动力与驱动** | 吸尘风机 · 驱动轮 · 底盘升降 | ~12% | ~11% | ~10% |
| 4 | **清洁功能** | 拖布 · 水泵 · 水箱 · 边/滚刷 | ~18% | ~16% | ~14% |
| 5 | **基站系统** | 集尘 · 水路 · 加热 · 电控 · 结构 | ~7% | ~15% | ~22% |
| 6 | **能源系统** | 电芯 · BMS · 充电 IC | ~9% | ~8% | ~8% |
| 7 | **整机结构 CMF** | 外壳 · 喷涂/IMD · 模具摊销 | ~13% | ~12% | ~11% |
| 8 | **MVA + 软件授权** | 组装 · 算法版税 · OS · 包材 · 物流 | ~20% | ~16% | ~13% |

整机 BOM 率参考：旗舰机 **48–55%** / 中档机 **40–48%** / 入门机 **35–42%**。

---

## Web UI（前端）

提供 **OCR 识别** 与 **数据库浏览** 两大核心界面，面向非工程同事（产品 / 采购 / 成本团队）。

### 技术栈

- **后端**：FastAPI（Python，复用 `core/` 现有模块）
- **前端**：Next.js 15 + React 19 + Tailwind + shadcn/ui
- **OCR（本地优先，不依赖云端）**：
  - 文字识别：**PaddleOCR**（中英文混合，PCB 丝印首选） / RapidOCR（纯本地、CPU 可跑）
  - 视觉理解（可选）：**Qwen2-VL-7B** / MiniCPM-V 2.6（本地 GPU 运行，识别元器件类型 / 封装）
  - 部署：推理服务独立容器（`web/ocr`），CPU 模式开箱即用，GPU 可选加速
- **图表**：Recharts（8 桶占比、价格趋势）
- **部署**：单机 docker-compose 起服（`web/api` + `web/ui` + `web/ocr`）

### 核心页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 仪表盘 | `/` | 平台概览：标准件库条数、拆机机型数、产品库规模、近期价格变动 |
| **OCR 识别** | `/ocr` | 上传拆机照片 → 识别 PCB 元器件丝印 → 自动匹配 `components_lib.csv` → 可编辑后入库 |
| 标准件库 | `/components` | 按桶 / 型号 / 供应商筛选；支持编辑、价格历史曲线、来源追溯 |
| 竞品产品库 | `/products` | 机型横向对比，配置标签（LDS/dToF、单/双泵、加热烘干...）筛选 |
| 拆机档案 | `/teardowns` | 每个机型的元器件清单 + FCC 原图查看 + 置信度标签 |
| BOM 分析 | `/bom` | 上传自家 BOM CSV → 8 桶占比可视化（**私有，需登录授权**） |

### OCR 识别工作流（前端）

**两种识别模式并存**，用户可按需选择：

**模式 A · 全图自动识别**（快速，粗查）

```
用户上传拆机/FCC 照片
   ↓
前端压缩 + 预览（多图批量支持）
   ↓
POST /api/ocr/recognize  (整图, mode=auto)
   ↓
FastAPI 调本地 PaddleOCR + SKU 模糊匹配
   ↓ 返回：[{bbox, text, candidate_skus[]}]
前端渲染：在图片上叠加 bbox + 识别文本
```

**模式 B · 用户框选 ROI 精准识别**（推荐，高精度）

```
用户上传图片后进入编辑模式
   ↓
在图像上拖拽画框选定元器件（支持多框 + 缩放 + 旋转微调）
   ↓
POST /api/ocr/recognize  (原图 + [{x, y, w, h}, ...], mode=roi)
   ↓
后端裁剪每个 ROI 区域 → PaddleOCR 识别 + 可选视觉模型判断封装
   ↓ 返回：每个框 → {text, component_type, candidate_skus[]}
前端渲染：
  - 每个用户框上叠加识别结果
  - 下拉候选 SKU（来自 components_lib.csv）
  - 允许用户编辑文本 / 改桶 / 补供应商
   ↓
用户点击"提交" → POST /api/ocr/commit
   ↓
写入 data/teardowns/fcc/{slug}/components.json
   可选：upsert 到 components_lib.csv
```

> **为什么要框选？** PCB 上元器件密集、丝印小、角度倾斜，全图 OCR 易漏检或误匹配。用户框选能限定 OCR 区域 → 大幅提升 Top-1 命中率（实测 40% → 85%+）。

### 数据浏览工作流

- 统一的 **DataTable 组件**（服务端分页 + 虚拟滚动）
- 全文搜索（`name` / `model_numbers` / `spec` / `suppliers`）
- 筛选器：桶、tier、confidence、供应商、最近更新时间
- **来源追溯**：点击条目查看 →「此价格来自哪次拆机 / 哪个爬虫 / 谁修改」
- **价格历史图**：从 `price_history.csv` 读取，Recharts 渲染折线

### 目录结构（建议）

```
web/
├── api/                        # FastAPI 后端
│   ├── main.py                 # 入口 + CORS
│   ├── routers/
│   │   ├── components.py       # GET /api/components  (分页/筛选/搜索)
│   │   ├── products.py         # GET /api/products
│   │   ├── teardowns.py        # GET /api/teardowns
│   │   ├── ocr.py              # POST /api/ocr/recognize · commit
│   │   ├── prices.py           # GET /api/prices/history/{sku}
│   │   └── bom.py              # POST /api/bom/analyze (鉴权)
│   └── services/
│       ├── ocr_service.py      # PaddleOCR 封装 + ROI 裁剪 + 全图两种模式
│       ├── vision_service.py   # 可选视觉模型（Qwen2-VL / MiniCPM-V）判断封装/类型
│       ├── sku_matcher.py      # OCR 文本 → components_lib SKU 模糊匹配
│       └── auth.py             # BOM 页面简单鉴权
│
├── ocr/                        # 本地 OCR 推理服务（独立容器）
│   ├── Dockerfile              # 预装 PaddleOCR / RapidOCR 权重
│   └── server.py               # gRPC / HTTP 接口，供 api 调用
│
├── ui/                         # Next.js App Router
│   ├── app/
│   │   ├── page.tsx            # 仪表盘
│   │   ├── ocr/page.tsx        # OCR 上传 + ROI 框选 + 审核
│   │   ├── components/page.tsx # 标准件库
│   │   ├── products/page.tsx
│   │   ├── teardowns/page.tsx
│   │   └── bom/page.tsx
│   ├── components/
│   │   ├── DataTable.tsx
│   │   ├── ImageAnnotator.tsx  # 图像框选交互（基于 react-konva / fabric.js）
│   │   ├── BBoxOverlay.tsx
│   │   └── BucketChart.tsx
│   └── lib/api.ts              # API 客户端
│
└── docker-compose.yml
```

### 实施建议（分三期）

1. **Phase 1（2 周）**：只读数据库浏览
   - `/components` `/products` `/teardowns` 三个 table + 基础筛选
   - 只读 API，无认证（内网部署）
2. **Phase 2（3 周）**：OCR 识别闭环
   - 上传 / ROI 框选 / 本地 OCR 识别 / SKU 模糊匹配 / 人工审核 / 入库
   - `price_history.csv` 曲线接入
3. **Phase 3（2 周）**：BOM 分析 UI
   - 上传 BOM CSV → 8 桶可视化 + 降本建议
   - 简单鉴权（仅内部项目组可见）

---

## 使用示例

### 本地测试（无 Anthropic API Key 时用 AIHUBMIX 兼容代理）

`gen_teardown.py` 的 web_agent 自动在两种 backend 间切换：

| 环境变量 | 走哪条路 |
|---|---|
| 设置了 `AIHUBMIX_API_KEY` | OpenAI-compatible（aihubmix / 任意兼容接口），模型由 `AIHUBMIX_MODEL` 指定 |
| 只有 `ANTHROPIC_API_KEY` | Anthropic 原生 + server-side web_search/web_fetch |

AIHUBMIX 走法示例（推荐本地测试用，成本低且无需翻墙）：

```bash
# 单次跑
AIHUBMIX_API_KEY=sk-xxx AIHUBMIX_MODEL=gpt-4o \
  python scripts/gen_teardown.py "卧安 K10+ Pro Combo"

# 持久写入当前 shell（一次性 export，后续命令直接跑）
export AIHUBMIX_API_KEY=sk-xxx
export AIHUBMIX_MODEL=gpt-4o         # 可选：默认 gpt-5.4-mini
# export AIHUBMIX_BASE_URL=...        # 可选：默认 https://aihubmix.com/v1
python scripts/gen_teardown.py "石头G30S Pro"

# 只跑 Stage 2-4（跳过爬虫，复用已有 CSV 调试审计逻辑）
python scripts/gen_teardown.py --csv data/teardowns/卧安K10+_20260422_teardown.csv "卧安K10+"

# 显式指定 MSRP（跳过自动查询，加快调试）
python scripts/gen_teardown.py --msrp 2999 "卧安 K10+ Pro Combo"
```

生成的 CSV 带日期后缀：`data/teardowns/{slug}_{YYYYMMDD}_teardown.csv`，便于版本对比。

### 命令行

```bash
# ② 竞品拆机
python scripts/gen_teardown.py "石头G30S Pro"
python scripts/fetch_fcc.py "追觅 X40 Ultra"
python scripts/build_components.py

# ③ 标准件库维护
python scripts/update_prices.py --bucket compute_electronics --dry-run
python scripts/update_prices.py

# ④ 8 桶框架对账 CSV（按需生成，不入库）
python scripts/export_framework_csv.py
```

### Agent 交互（接入 OpenClaw 后）

统一使用 `/命令` 快捷方式，详见 [`SKILL.md`](SKILL.md#常用命令)。

| 命令 | 用途 | 示例 |
|------|------|------|
| `/bom <品牌> <型号>` | BOM 完整分析（核心命令） | `/bom 石头 G30S Pro` |
| `/parts <关键词>` | 零部件跨机型查询 | `/parts 越障 4cm 驱动轮电机` |
| `/cut <品牌> <型号>` | 降本机会识别 | `/cut 石头 G20S` |
| `/vs <A> vs <B> [--bucket <桶>]` | 子系统/整机对标 | `/vs 石头P10pro vs 科沃斯X2pro --bucket dock_station` |
| `/find <关键词\|桶>` | 数据库直查 | `/find SoC`（或 `/find compute_electronics`） |
| `/framework` | 导出 8 桶对账 CSV | `/framework` |

> 仍兼容自然语言输入（如"石头 G30S Pro，分析 BOM 成本"），Agent 自动解析为对应命令。

### Web UI

```bash
cd web && docker-compose up -d
# 浏览器打开 http://localhost:3000
```

---

## 功能特性建议（路线图）

### 🔥 短期（1–2 个月，打通闭环）

1. **FCC / 拆机图 OCR 识别**（本地方案，填补 `fetch_fcc.py` 缺口 + Web UI 承载）
   - **本地 OCR**：PaddleOCR / RapidOCR 识别 PCB 元器件丝印（型号、封装、丝印文字），CPU 可跑
   - **用户 ROI 框选**：Web UI 支持画框选定元器件区域，裁剪后单独识别，命中率 40%→85%+
   - **可选视觉模型**：Qwen2-VL / MiniCPM-V 本地部署，辅助判断封装类型（QFN/BGA/SOT...）
   - 自动映射 `components_lib.csv` 已有 SKU，未命中时生成"待确认"条目
   - 输出 `data/teardowns/fcc/{slug}/components.json`（含坐标、置信度、分类建议）

2. **前端 Phase 1**：数据库浏览页面（`/components` `/products` `/teardowns`）

3. **成本差异 Diff 工具**（`scripts/compare_bom.py`）
   - 输入两个机型，输出 8 桶并排表 + 差异件清单 + "若替换可节省 ¥X"

4. **降本建议引擎**（`scripts/optimize_bom.py`）
   - 扫描 BOM 识别溢价件（单价 > 同桶 P75 或有更便宜替代）
   - 推荐 2–3 个替代方案 + 节省金额估算 + 风险提示

### ⚡ 中期（3–6 个月，规模化数据）

5. **前端 Phase 2/3**：OCR 识别闭环 + BOM 分析可视化

6. **市场调研自动化**（扩展 `import_products.py`）
   - 爬京东/天猫/亚马逊/Reddit，抓取新品规格、售价、评分
   - 识别配置代际（LDS→dToF、单泵→双泵）作为标签
   - 生成月度行业简报

7. **动态价格爬虫稳定化**（`update_prices.py`）
   - 源：立创商城 + 1688 + Digi-Key + 阿里国际
   - 每周全量 + 按需触发；波动 > 20% 时告警

8. **置信度 & 数据血缘**
   - 每个 SKU 记录来源链（哪次拆机 / 哪个爬虫 / 人工修改）
   - Agent 答复附来源

9. **子系统基准库**（跨机型横向数据）
   - "基站系统 × 档位"、"感知 × 配置" 基准曲线

### 🚀 长期（6+ 个月，平台化）

10. **物料替代知识图谱**：节点=SKU，边=替代关系（性能等级 / 供应风险 / 封装兼容）

11. **整机 ROI 模拟器**：输入目标零售价+毛利率，倒推 BOM 上限 + 各桶预算

12. **多机型项目协同**：共用件抽取、新机型立项标杆 BOM 模板

13. **飞书双向同步**：从单向写改为双向，便于非工程同事维护

14. **合规 & IP 预警**：识别专利授权件，打 `license_risk` 标

---

## 安装（OpenClaw）

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

### 飞书同步（可选）

编辑 `config.yaml`：

```yaml
feishu:
  product_obj_token: ""
  teardown_obj_token: ""
  components_obj_token: ""

local:
  product_csv: ""
```

> `obj_token` 即多维表格的 `app_token`；Wiki 嵌入的表格需先解析。
> `config.yaml` 已在 `.gitignore` 内。
