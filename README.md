# unit-bot

**扫地机器人 BOM 成本分析平台** — 竞品拆机 · 8 桶成本核算 · FCC 采集 · 降本优化

- 语言：Python 3.10+
- 接入：OpenClaw / 飞书 / Slack / CLI
- 数据：`data/` 目录私有，框架模板和型号映射公开入 git
- 授权：内部工具，非公开发布

---

## 面向用户

| 用户 | 典型场景 |
|------|---------|
| **产品 / 成本团队** | `/bom 石头 G30S Pro` 得到 8 桶占比报告 + 降本建议 |
| **供应链 / 采购** | `/cut 追觅 X40` 识别溢价件 + 替代方案 + 节省金额 |
| **研发 / 硬件** | `/vs A vs B --bucket compute_electronics` 子系统技术对标 |
| **数据维护** | 维护三类数据库：`products.csv` 产品规格库 · 拆机档案（`gen_teardown.py` 产出 + `/fcc find/ocr` FCC 上游）· `components_lib.csv` 标准件库 |

---

## 核心能力

- **4-Stage 拆机 Pipeline**：web 调研 → SoC 伴随件推导 → 覆盖率审计 → 三级查价，产出 8 桶 BOM 报告
- **FCC 两步采集**：`find` 查文档链接（不下载）→ 人工确认 → `ocr` 下载 PDF + 视觉识别芯片丝印
- **标准件库**：200+ SKU，三层定价（权威 → fallback → 桶兜底），动态价格爬取
- **8 桶框架单一事实源**：`bom_8bucket_framework.json` 改一处，四处消费方自动同步
- **型号别名匹配**：国内/海外型号自动映射，支持模糊搜索
- **飞书单向同步**：分析结果写入多维表格（可选，未配置时静默跳过）

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
/bom 石头 G30S Pro
```

Agent 自动完成：查规格 → 爬元器件 → 8 桶成本 → 供应链替代 + 竞品对比。输出拆机 CSV + 控制台报告。

### 路径 B · CLI 直接运行

```bash
# 1. 采集 FCC 文档（可选，有 FCC 数据时 Stage 0 优先使用）
python scripts/fetch_fcc.py find "石头G30S Pro"   # 查链接，供人工确认
python scripts/fetch_fcc.py ocr  "石头G30S Pro"   # 确认后下载 PDF + OCR

# 2. 生成拆机 BOM（4-Stage）
python scripts/gen_teardown.py "石头G30S Pro"

# 3. 更新标准件库价格（可选）
python scripts/update_prices.py --dry-run
python scripts/update_prices.py
```

### 路径 C · 本地调试（AIHUBMIX 代理，免翻墙、成本低）

```bash
export AIHUBMIX_API_KEY=sk-xxx
export AIHUBMIX_MODEL=gpt-4o          # 默认 gpt-4.1-mini

python scripts/gen_teardown.py "卧安 K10+ Pro Combo"

# 跳过爬虫，复用已有 CSV 调试 Stage 2-4
python scripts/gen_teardown.py --csv data/teardowns/卧安K10+_20260422_teardown.csv "卧安K10+"

# 指定 MSRP，跳过自动查询
python scripts/gen_teardown.py --msrp 2999 "卧安 K10+ Pro Combo"
```

---

## 命令参考

### `/bom <品牌> <型号>`

BOM 完整分析，核心命令。

```
/bom 石头 G30S Pro
/bom 追觅 X40 Ultra
```

Agent 执行 7 步流程：查已有数据 → 型号别名解析 → 补规格层 → 4-Stage 拆机 BOM → 8 桶成本分析 → 供应链+降本 → 竞品差异对标。

输出：
- `data/teardowns/{slug}_{date}_teardown.csv`
- 控制台：8 桶占比 · BOM/MSRP 比 · 偏差告警 · 技术亮点 · 替代建议

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


### `/cut <品牌> <型号>`

降本机会识别，匹配 `components_lib.csv` 中 `tier=premium` 的件。

```
/cut 石头 G20S
```

输出：溢价件列表 · 替代方案 · 节省金额估算 · 替换风险提示

---

### `/vs <A> vs <B> [--bucket <桶>]`

子系统或整机对标。

```
/vs 石头P10pro vs 科沃斯X2pro
/vs 科沃斯 X8 Pro vs 石头 S8 MaxV Ultra --bucket dock_station
```

不带 `--bucket` 则整机 8 桶并排。带 `--bucket` 则按该桶的 `typical_items` 逐项对比。

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

按需导出 8 桶对账 CSV，不入 git，用于填价对账。

```
/framework
```

产出：`data/lib/bom_8bucket_framework.csv`

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | — | Anthropic 原生 API，走 server-side web_search |
| `AIHUBMIX_API_KEY` | — | OpenAI-compatible 代理（优先级高于 Anthropic） |
| `AIHUBMIX_MODEL` | `gpt-4.1-mini` | 指定代理使用的模型 |
| `AIHUBMIX_BASE_URL` | `https://aihubmix.com/v1` | 代理 base URL |

> 两个 API Key 同时存在时，优先走 `AIHUBMIX_API_KEY`。

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
| 8 桶框架 | `core/bom_8bucket_framework.json` | 单一事实源 |

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
│   ├── bucket_framework.py     # 8 桶框架加载器
│   ├── bom_8bucket_framework.json  # ★ 8 桶标准模板（单一事实源）
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
│   ├── build_components.py     # 拆机 CSV → components_lib.csv
│   ├── update_prices.py        # 动态爬价
│   ├── export_framework_csv.py # 8 桶对账 CSV（按需）
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

### 常用调试命令

```bash
# 跳过爬虫，复用已有 CSV 调试 Stage 2-4
python scripts/gen_teardown.py --csv data/teardowns/卧安K10+_20260422_teardown.csv "卧安K10+"

# 动态爬价演习（不写入）
python scripts/update_prices.py --bucket compute_electronics --dry-run

# 导出 8 桶对账表
python scripts/export_framework_csv.py
```

---

## 参考资料

- [fccid.io](https://fccid.io) — FCC 申请文档检索
- [fcc.report](https://fcc.report) — FCC 文档 PDF 直链
- [立创商城](https://www.szlcsc.com) · [Digi-Key](https://www.digikey.cn) · [1688](https://www.1688.com) — 动态价格来源
- [`SKILL.md`](SKILL.md) — OpenClaw skill 完整文档（Pipeline 细节 / 置信度层级 / 8 桶框架字段说明）

---

## 当前进度（2026-04）

### ✅ 已完成

- **8 桶框架定型**：8 类成本桶 + 入门/中档/旗舰三档基准占比，单一事实源。
- **标准件库**：200+ SKU，三层定价，动态爬价框架。
- **FCC 两步工作流**：`find`（查链接）+ `ocr`（识别），两步解耦支持人工干预。
- **型号别名匹配**：国内/海外型号自动映射，支持模糊搜索。
- **飞书单向同步**：分析结果推送到多维表格，未配置时静默跳过。
- **首个 BOM 样例打通**：938 行原始 BOM → 416 计价单元，5/8 桶占比落在 ±5% 基准区间。

### 🚧 进行中

- FCC OCR 元器件自动归类（视觉模型识别 PCB 芯片丝印）
- Web UI（PaddleOCR 本地识别 + 数据库浏览界面）
- 动态价格爬取稳定化（立创 / Digi-Key / 1688 数据源）

### 📋 待办

- 成本差异可视化（桶级柱状图、机型并排 diff）
- 降本建议引擎（溢价件识别、替代方案、节省金额估算）
- 更多品牌 / 海外市场型号别名覆盖
