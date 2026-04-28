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

| 命令 | 用途 | 示例 |
|------|------|------|
| `/bom <品牌> <型号>` | BOM 完整分析（核心命令） | `/bom 石头 G30S Pro` |
| `/fcc find <品牌> <型号>` | 查找 FCC 文档链接（不下载） | `/fcc find 石头 G30S Pro` |
| `/fcc ocr <品牌> <型号>` | 下载 PDF + OCR 识别零件 | `/fcc ocr 石头 G30S Pro` |
| `/cut <品牌> <型号>` | 降本机会识别 | `/cut 石头 G20S` |
| `/vs <A> vs <B> [--bucket <桶>]` | 子系统 / 整机对标 | `/vs 科沃斯X8Pro vs 石头S8MaxV --bucket dock_station` |
| `/find <关键词\|桶>` | 数据库直查 | `/find SoC`（或 `/find compute_electronics`） |
| `/framework` | 导出 8 桶对账 CSV | `/framework` |

---

## 命令详解

### `/bom <品牌> <型号>`
> `/bom 石头 G30S Pro`

4-Stage Pipeline 全流程：查规格 → 爬元器件 → 8 桶成本 → 供应链替代 + 竞品差异。

输出：拆机 CSV · 8 桶占比报告 · BOM/MSRP 比 · 溢价件替代建议 · 相近价位竞品对比。

### `/fcc find <品牌> <型号>`
> `/fcc find 石头 G30S Pro`

在 fccid.io 匹配 FCC ID，列出全部文档的页面链接和 PDF 直链，写入 `links.json`。**不下载**，方便先在浏览器确认文档质量。

### `/fcc ocr <品牌> <型号>`
> `/fcc ocr 石头 G30S Pro`

读取 `links.json`（不存在时自动先 find），下载 Internal Photos / Parts List PDF，逐页视觉 OCR 识别芯片丝印，去重后写入 `latest.json` + 上游 CSV（`gen_teardown.py` Stage 0 自动读取）。

### `/cut <品牌> <型号>`
> `/cut 石头 G20S`

匹配 `components_lib.csv` 中 `tier=premium` 的件，给出替代方案 + 节省金额估算。

### `/vs <A> vs <B> [--bucket <桶>]`
> `/vs 科沃斯 X8 Pro vs 石头 S8 MaxV Ultra --bucket dock_station`

按指定桶的 `typical_items` 逐项对比；省略 `--bucket` 则整机 8 桶并排。

### `/find <关键词|桶>`
> `/find CPU`（或 `/find compute_electronics`）

遍历 `data/teardowns/*.csv`，按关键词或桶名抽取匹配条目。

### `/framework`
> `/framework`

运行 `export_framework_csv.py`，产出 `data/lib/bom_8bucket_framework.csv`（按需生成，不入库，填价对账用）。

---

## 数据源配置（`config.yaml`）

所有路径可在根目录 `config.yaml` 中覆盖，未配置时使用以下约定路径：

| 域 | 文件 / 目录 | 说明 |
|---|---|---|
| 产品数据库 | `data/products/products.csv` · `products_db.json` | MSRP / 规格 / 功能 |
| 拆机数据 | `data/teardowns/{slug}_{YYYYMMDD}_teardown.csv` | `gen_teardown.py` 产出 |
| FCC 上游 | `data/teardowns/fcc/{slug}/{slug}_fcc_{date}.csv` | `fetch_fcc.py` 产出，Stage 0 优先上游 |
| 标准件库 | `data/lib/components_lib.csv` | 权威定价（人工维护） |
| 基准价库 | `data/lib/standard_parts.json` | SoC 参考表 / 伴随件 heuristics |
| 型号映射 | `data/products/model_aliases.csv` | 国内/海外别名（人工维护，入 git） |
| **8 桶框架** | `core/bom_8bucket_framework.json` | 单一事实源 |

> 飞书同步为可选展示层（只写不读），未配置时静默跳过。

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

## Pipeline 详细：`gen_teardown.py` 4-Stage

| Stage | 职责 | 关键产出 |
|-------|------|---------|
| **0 FCC 上游** | 自动载入 `fcc/{slug}/*_fcc_*.csv`（有则注入，无则跳过） | 已知 FCC 件不重复爬取 |
| **1 Discovery** | 多源调研爬元器件型号；prompt 注入桶定义 + 典型子项 + boundary_notes + 合法桶白名单 | `bom_bucket + name + model + confidence + source_url` |
| **2 Enrichment** | SoC 推导伴随件：识别到 RK3588S 等自动补 PMIC/RAM/ROM/AI 授权 | 补齐易漏配套件 |
| **2.5 Normalize** | LLM 自创桶名（如 `perception_system`）映射回 framework 8 个合法 key | 兜底保护 |
| **3 Coverage Audit** | 对照 `typical_items` 逐桶检查；缺失率 >60% 告警 | 缺失关键子项清单 |
| **4 Aggregate & Bias** | 三级查价（`components_lib` → `standard_parts` → 桶兜底）；桶占比 vs 基准 ±tolerance；BOM/MSRP 诊断 | BOM 合计 · 桶占比 · 偏差告警 |

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

## BOM 8 桶框架

单一事实源：`core/bom_8bucket_framework.json`，通过 `core/bucket_framework.py` 加载。修改一处，gen_teardown / analyze / export_csv 四处自动同步。

| # | 桶 | 核心内容 | 行业基准 |
|---|---|---------|---------|
| 1 | 算力与电子 | SoC · MCU · Wi-Fi/BT · PMIC · RAM/ROM · PCB · 阻容 | 11% (10–15%) |
| 2 | 感知系统 | LDS · ToF · 前视线激光 · IMU · 沿墙 · 超声波 · 碰撞 | 11% (10–15%) |
| 3 | 动力与驱动 | 主机吸尘风机 · 驱动轮/履带 · 边轮 · 万向轮 · 越障升降 | 10% (8–13%) |
| 4 | 清洁功能 | 拖布本体 · 滚刷 · 边扫 · 主机水箱/尘盒 · 清水泵 | 14% (12–16%) |
| 5 | 基站系统 | 外壳 · 电源 · 集尘 · 清水/污水桶 · PTC · 顶杆 · PCBA | 22% (18–28%) ¹ |
| 6 | 能源系统 | 锂电池包（电芯 + BMS + 封装） | 8% (5–10%) |
| 7 | 整机结构 CMF | 上盖/底盘 · CMF 喷涂 · 模具摊销 · 紧固件 | 11% (9–13%) |
| 8 | MVA + 软件授权 | 组装+外协 · SLAM 版税 · QA · 包材 · 物流 · OS | 13% (10–16%) |

> ¹ 基站占比分档：纯充电桩 ~5%、含换水 +10%、含集尘 +8%、含自清洗 +5%。
> 整机 BOM/MSRP 比例常见 **25–40%**（旗舰机偏上限）。

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
