# unit-bot

扫地机器人 BOM 成本分析平台，支持竞品拆机成本核算、降本优化建议、供应链分析。

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/fifteenbao/unit-bot
cd unit-bot
pip install -r requirements.txt
```

配置 API Key（三选一，优先级从高到低）：

```bash
export AIHUBMIX_API_KEY=sk-xxx    # 推荐：带服务端 web_search
export DEEPSEEK_API_KEY=sk-xxx    # 备选：客户端 DuckDuckGo 搜索
export ANTHROPIC_API_KEY=sk-xxx   # 兜底：需能直连 Anthropic
```

启动：

```bash
python agent.py
```

### 2. 接入 OpenClaw（免配置 API Key）

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

> OpenClaw 在运行时自动注入 `OPENCLAW_API_KEY`，无需额外配置。

---

## 命令

### 核心工作流

分析一款新机型，按顺序执行：

```
/product 石头 G30S Pro      ← 第一步：采集规格，写入产品库
/bom     石头 G30S Pro      ← 第二步：生成 7 桶成本报告
/dfma    石头 G30S Pro      ← 第三步：输出降本建议
```

| 命令 | 做什么 | 不做什么 |
|------|--------|---------|
| `/product <品牌> <型号>` | 多源采集 30+ 规格参数，写入产品库 | 不做成本分析 |
| `/bom <品牌> <型号>` | 7 桶成本报告 + 整机成本结构 + 供应链风险 | 不给降本建议 |
| `/dfma <品牌> <型号>` | 功能-成本矩阵 + DFMA 设计抓手 + 降本潜力 | 需先跑过 `/bom` |
| `/fcc find <品牌> <型号>` | 查找 FCC 文档链接（不下载） | — |
| `/fcc ocr <品牌> <型号>` | 下载 FCC PDF + OCR 识别 PCB 芯片丝印 | — |

> **`/fcc` 是可选步骤**。有 FCC 数据时 `/bom` 的 Stage 0 会自动加载，芯片识别更准确；没有也能正常运行。

### 辅助命令

| 命令 | 用途 |
|------|------|
| `/cut <品牌> <型号>` | 识别溢价件，给出件级替代方案（与 `/dfma` 互补） |
| `/vs <A> vs <B> [--bucket <桶>]` | 两机型 7 桶并排对标，或指定子系统逐项对比 |
| `/find <关键词\|桶名>` | 搜索 teardown 档案和标准件库 |
| `/framework` | 导出 7 桶对账 CSV（填价用，不入 git） |

### 等价脚本（批量 / 自动化场景）

```bash
# 批量导入产品规格
python scripts/import_products.py data/products/products.csv

# 生成拆机 BOM（可指定零售价，或复用已有 CSV 跳过网络调研）
python scripts/gen_teardown.py "石头G30S Pro"
python scripts/gen_teardown.py "石头G30S Pro" --msrp 5999
python scripts/gen_teardown.py --csv data/teardowns/xxx.csv "xxx"

# FCC 文档采集
python scripts/fetch_fcc.py find "石头G30S Pro"
python scripts/fetch_fcc.py ocr  "石头G30S Pro"

# 分析制造 BOM（金蝶/SAP 导出格式）
python scripts/cost_mfg_bom.py data/bom/xxx.csv --msrp 2999
```

---

## 成本框架

### 整机成本 4 级分解

`/bom` 的输出按以下层级组织，从宏观到零件逐层展开：

| 层级 | 内容 |
|------|------|
| **一级：成本大类** | 硬件物料 · 人工+机器折旧 · 销售+管理费用 · 研发均摊 · 仓储物流售后 |
| **二级：7 桶** | 算力与电子 / 感知系统 / 动力与驱动 / 清洁功能 / 基站系统 / 能源系统 / 整机结构CMF |
| **三级：功能模块** | 每桶下的物理子系统（导航模组、清洁组件、驱动系统等） |
| **四级：组件** | 最小可计价单元，对应 BOM 一行（单颗芯片、单个电机、单张 PCB） |

### 一级成本占比参考

> 来源：开源证券·科沃斯 T80S 拆解（2024）

| 大类 | 行业区间 | T80S 实测 |
|------|---------|----------|
| 硬件物料（7 桶） | 40–55% | 约 42.5% |
| 人工+机器折旧 | 6–12% | 约 7.5% |
| 销售+管理费用 | 20–35% | 约 25% |
| 研发均摊 | 3–8% | 约 4.4% |
| 仓储物流售后 | 6–12% | 约 7.5% |

### 7 桶基准占比

> T80S 实测校准，含基站全配置机型偏上限

| 桶 | 基准占比 |
|----|---------|
| 算力与电子 | ~13% |
| 感知系统 | ~16% |
| 动力与驱动 | ~11% |
| 清洁功能 | ~20% |
| 基站系统 | ~24% |
| 能源系统 | ~7% |
| 整机结构CMF | ~13% |

---

## 数据架构

系统维护 5 类数据，各自回答不同层面的问题：

| 数据库 | 文件 | 回答什么问题 |
|--------|------|------------|
| ① 产品规格库 | `data/products/products_db.json` | 这台机器**是什么** |
| ② 拆机档案 | `data/teardowns/{slug}_{date}_teardown.csv` | 这台机器**用了什么件** |
| ③ 标准件库 | `data/lib/components_lib.csv` | 这类件**值多少钱** |
| ④ 材料库 | `data/lib/materials.csv` | 原材料**怎么定价** |
| ⑤ 供应商库 | `data/lib/suppliers.csv` | **谁在供货** |

**数据流**：

```
/product → ①产品库 ──┐
                      ├──→ /bom ──→ /dfma
/fcc ocr → ②拆机档案 ─┘    ↑
                       ③标准件库（查价）
                       ④材料库  （原料单价）
                       ⑤供应商库（供应链）
```

### 标准件库入库规则

`components_lib.csv` 仅接受高置信度来源：

| 来源 | 入库 |
|------|------|
| 人工/实物核实（`confirmed`） | ✓ |
| 实物拆机 CSV（`teardown`） | ✓ |
| FCC 文档 OCR（`fcc`） | ✓ |
| 启发式推导（`inferred`） | ✗ |
| 行业基准估算（`estimate`） | ✗ |
| 网络调研（`web`） | ✗ |

> 跑完 `/fcc ocr` 后直接执行 `python scripts/build_components.py` 即可入库，无需先跑 `/bom`。

### 数据维护入口

| 要改什么 | 在哪里改 |
|---------|---------|
| 桶定义 / 典型子项 / 基准占比 | `core/bom_8bucket_framework.json` |
| 一级成本参考值 | `core/bom_8bucket_framework.json` → `level1_categories` |
| 零件价格 | `data/lib/components_lib.csv` → `cost_min` / `cost_max` |
| 原材料单价 | `data/lib/materials.csv` → `price_min` / `price_max` |
| 供应商信息 | `data/lib/suppliers.csv` → `tier` / `payment_terms` |
| 型号别名 | `data/products/model_aliases.csv` |
| 新增竞品规格 | `data/products/products.csv` → `python scripts/import_products.py` |

---

## 项目结构

```
unit-bot/
├── SKILL.md          # OpenClaw skill 元数据 + 命令文档
├── agent.py          # Agent 主循环
├── config.yaml       # 路径配置
│
├── core/
│   ├── bom_8bucket_framework.json   # ★ 7 桶模板（单一事实源）
│   ├── bucket_framework.py
│   ├── bom_rules.py                 # 归桶规则
│   ├── components_lib.py
│   ├── materials_lib.py
│   ├── auxiliary_parts.py
│   ├── db.py
│   └── feishu_sync.py               # 飞书同步（可选）
│
├── scripts/
│   ├── gen_teardown.py              # 拆机 4-Stage Pipeline
│   ├── cost_mfg_bom.py             # 制造 BOM 成本分析
│   ├── fetch_fcc.py
│   ├── import_products.py
│   ├── build_components.py
│   └── export_framework_csv.py
│
└── data/
    ├── lib/
    │   ├── components_lib.csv       # 权威查价表（200+ SKU）
    │   ├── standard_parts.json
    │   ├── materials.csv            # 原材料单价（22 种）
    │   └── suppliers.csv            # 供应商库（37 家）
    ├── products/
    │   ├── model_aliases.csv        # 入 git
    │   └── products_db.json         # 私有
    └── teardowns/
        ├── {slug}_{YYYYMMDD}_teardown.csv
        └── fcc/{slug}/
```

---

## 参考资料

- [SKILL.md](SKILL.md) — 完整命令文档（Pipeline 细节 / 置信度层级 / 7 桶字段说明）
- [fccid.io](https://fccid.io) · [fcc.report](https://fcc.report) — FCC 文档检索
- [立创商城](https://www.szlcsc.com) · [Digi-Key](https://www.digikey.cn) · [1688](https://www.1688.com) — 动态价格来源
- 开源证券·科沃斯 T80S 成本拆解（2024）— 一级成本占比数据来源
