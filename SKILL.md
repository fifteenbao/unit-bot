---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"]}}
---

# unit-bot — 扫地机器人 BOM 成本分析与技术选型

## 单一事实源：`core/bom_8bucket_framework.json`

本 skill 的所有 BOM 分析逻辑均来自 `core/bom_8bucket_framework.json`，通过
`core/bucket_framework.py` 加载器消费。每个字段都有对应消费点：

| JSON 字段 | 消费点 |
|-----------|--------|
| `buckets.*.name_cn` / `name_en` | 控制台表头、对账 CSV |
| `buckets.*.order` | 桶打印顺序 |
| `buckets.*.definition` | Stage 1 prompt 桶定义 |
| `buckets.*.typical_items[].name` | Stage 3 覆盖审计、Stage 1 prompt 子项清单 |
| `buckets.*.typical_items[].example_spec` | Stage 1 prompt 典型规格提示 |
| `buckets.*.industry_pct_avg` / `industry_pct_range` | Stage 4 占比基准 + 合格区间 |
| `buckets.*.boundary_notes` | Stage 1 prompt 归桶边界（全量注入） |
| `validation_rules.bucket_pct_tolerance` | Stage 4 占比偏差容差 (±%) |
| `validation_rules.expected_bom_msrp_ratio_pct` | Stage 4 BOM/MSRP 合理区间诊断 |

修改模板 **一处**，下列四处自动同步：

- `scripts/gen_teardown.py` — Stage 1 prompt / Stage 2.5 桶名归一化 / Stage 3 覆盖审计 / Stage 4 占比基准+容差+BOM比
- `scripts/analyze_*.py` — 成本分桶 + 占比校验
- `scripts/export_framework_csv.py` — 按需生成对账 CSV（不入库）
- 其他 Agent 工具 — 通过 `from core.bucket_framework import ...` 直接消费

---

## 数据源配置（`config.yaml`）

所有路径可在 `config.yaml` 中覆盖，Skill 默认读取根目录 `config.yaml`。未配置时使用以下约定路径：

| 域 | 文件 / 目录 | 说明 |
|---|---|---|
| 产品数据库 | `data/products/products.csv` · `products_db.json` | MSRP / 规格 / 功能 |
| 拆机数据 | `data/teardowns/{slug}_{YYYYMMDD}_teardown.csv` | `gen_teardown.py` 产出（日期后缀版本追溯） |
| FCC 资料 | `data/teardowns/fcc/{slug}/` | `fetch_fcc.py` 独立采集 |
| 标准件库 | `data/lib/components_lib.csv` | 权威定价（人工维护） |
| 基准价库 | `data/lib/standard_parts.json` | 未收录件 fallback |
| 型号映射 | `data/lib/model_aliases.json` | 国内/海外别名 |
| **8 桶框架** | `core/bom_8bucket_framework.json` | 单一事实源 |

> 飞书同步为可选展示层（只写不读），未配置时静默跳过。

---

## 核心命令：`[品牌][型号]，分析 BOM 成本`

### 示例：`石头 G30S Pro，分析 BOM 成本`

Agent 自动执行 7 步流程：

| # | 动作 | 工具 / 脚本 | 数据依赖 |
|---|------|------------|---------|
| 1 | 查已有数据 | `get_product_detail` · `get_missing_data` | `products_db.json` + `data/teardowns/` |
| 2 | 型号别名解析 | `core.model_aliases` | `data/lib/model_aliases.json` |
| 3 | 补规格层 | `crawl_product_specs` (web_search/web_fetch) | — |
| 4 | 生成拆机 BOM | `scripts/gen_teardown.py` (4-Stage) | `core/bom_8bucket_framework.json` · `components_lib.csv` |
| 5 | 8 桶成本分析 | Stage 4 自动输出 | framework 基准占比 + `components_lib.csv` |
| 6 | 供应链 + 降本分析 | `match_bom_to_library` | `components_lib.csv`（溢价件识别 + 替代方案） |
| 7 | 竞品差异对标 | `compare_by_spec` | `products_db.json` 相近价位 2–3 款 |

输出：
- 拆机 CSV → `data/teardowns/石头G30SPro_20260422_teardown.csv`
- 控制台：4 阶段审计报告 + BOM 合计 + BOM/MSRP 比 + 占比偏差告警
- 技术亮点（3–5 条）· 供应链替代建议 · 竞品差异点

---

## Pipeline 详细：`gen_teardown.py` 4-Stage

| Stage | 职责 | 关键产出 |
|-------|------|---------|
| **1 Discovery** | 多源调研爬元器件型号；prompt 动态注入 framework 的桶定义 + 典型子项(含 example_spec) + 全部 boundary_notes + 合法 `bom_bucket` 白名单 | 每件 `bom_bucket + name + model + confidence + source_url` |
| **2 Heuristic Enrichment** | SoC 推导伴随件：识别到 RK3588S 等自动补 PMIC/RAM/ROM/AI 授权 | 补齐易漏配套件 |
| **2.5 Normalize** | 把 LLM 自创桶名(如 `perception_system`)通过别名表映射回 framework 8 个合法 key | 兜底保护 |
| **3 Coverage Audit** | 对照 framework `typical_items` 逐桶检查覆盖；缺失率 >60% 标记告警 | 缺失关键子项清单 |
| **4 Aggregate & Bias** | 三级查价 (components_lib → standard_parts → 桶兜底)；按桶汇总金额 vs framework `industry_pct_avg ± bucket_pct_tolerance`；BOM/MSRP 比对照 `expected_bom_msrp_ratio_pct` | BOM 合计 · 桶占比 · BOM/MSRP 诊断 · 偏差告警 |

> **定价维护**：更新 `data/lib/components_lib.csv` 的 `cost_min/cost_max`，下次跑 Stage 4 自动生效。不需要重启。

---

## FCC 数据采集（独立前置）

```bash
python scripts/fetch_fcc.py "石头G30S Pro"                   # 默认采集 + OCR
python scripts/fetch_fcc.py "科沃斯X8 Pro" --fcc-id 2A6HE-DEX8PRO
python scripts/fetch_fcc.py "石头P20 Ultra Plus" --force     # 忽略缓存重抓
python scripts/fetch_fcc.py "石头S91COP02" --download-only   # 只下载 PDF
```

输出：`data/teardowns/fcc/{slug}/latest.json` + `pdfs/`。FCC 数据与 `gen_teardown.py` **解耦**，作为 PCB 芯片识别的独立补充。

**支持品牌**：石头 Roborock · 追觅 Dreame · 科沃斯 Ecovacs · 云鲸 Narwal · SwitchBot 卧安 · 3irobotics 杉川 · Eufy 安克 · Xiaomi 小米 · iRobot

---

## BOM 8 桶框架（与 `core/bom_8bucket_framework.json` 同源）

| # | 桶 | 核心内容 | 行业基准 |
|---|---|---------|---------|
| 1 | 算力与电子 | SoC · MCU · Wi-Fi/BT · PMIC · RAM/ROM · PCB · 阻容 | 11% (10-15%) |
| 2 | 感知系统 | LDS · ToF · 前视线激光 · IMU · 沿墙 · 超声波 · 碰撞 | 11% (10-15%) |
| 3 | 动力与驱动 | 主机吸尘风机 · 驱动轮/履带 · 边轮 · 万向轮 · 越障升降 | 10% (8-13%) |
| 4 | 清洁功能 | 拖布本体 · 滚刷 · 边扫 · 主机水箱/尘盒 · 清水泵 | 14% (12-16%) |
| 5 | 基站系统 | 外壳 · 电源 · 集尘 · 清水/污水桶 · PTC · 顶杆 · PCBA | 22% (18-28%) ¹ |
| 6 | 能源系统 | 锂电池包（电芯+BMS+封装） | 8% (5-10%) |
| 7 | 整机结构 CMF | 上盖/底盘 · CMF 喷涂 · 模具摊销 · 紧固件 | 11% (9-13%) |
| 8 | MVA + 软件授权 | 组装+外协 · SLAM 版税 · QA · 包材 · 物流 · OS | 13% (10-16%) |

> ¹ 基站占比分档：纯充电桩 ~5%、含换水 +10%、含集尘 +8%、含自清洗 +5%。详见 framework `boundary_notes`。

整机 BOM/MSRP 比例常见 **25–40%**（旗舰机偏上限）。

---

## 常用命令

**BOM 完整分析**
> 石头 G30S Pro，分析 BOM 成本
→ 4-Stage Pipeline + 8 桶成本 + 供应链替代 + 竞品差异

**零部件跨机型查询**
> 越障 4cm 的产品用了哪些驱动轮电机？
→ 从 `data/teardowns/` 聚合，列机型 + 型号 + 供应商

**降本机会**
> 石头 G20S，哪些件是溢价件，降本空间在哪里？
→ 匹配 `components_lib.csv` tier=premium，给替代方案 + 节省金额估算

**子系统对标**
> 对比科沃斯 X8 Pro 和石头 S8 MaxV Ultra 的基站系统成本
→ 按 dock_station 桶 typical_items 逐项对比

**数据库直查**
> 列出所有拆机数据中出现过的 CPU 型号
→ 遍历 `data/teardowns/*.csv` 抽取 compute_electronics 桶

**生成对账 CSV**
> 导出 8 桶框架对账表
→ 运行 `python scripts/export_framework_csv.py`，产出 `data/lib/bom_8bucket_framework.csv`（不入库，填价对账用）

---

## 维护入口

| 入口 | 场景 | 示例 |
|------|------|------|
| `core/bom_8bucket_framework.json` | 调整桶定义/典型子项/基准占比 | 加入新的感知类型、修改占比区间 |
| `data/lib/components_lib.csv` | 日常价格维护 | 供应商报价更新 `cost_min/cost_max` |
| `data/lib/standard_parts.json` | 未收录件基准价 | 新增通用物料 fallback |
| `data/lib/model_aliases.json` | 国内/海外型号映射 | 新机型发布时补映射 |
| `data/products/products.csv` | 新增机型规格 | 竞品调研后批量导入 |

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

> `inferred` 数据需实物拆机核实后方可升级为 `confirmed`。
