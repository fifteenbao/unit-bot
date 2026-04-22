---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"]}}
---

# unit-bot — 扫地机器人 BOM 成本分析与技术选型

## 数据库配置（可选）

**所有数据默认保存在本地 `data/` 目录**，飞书多维表格仅作为前端展示层（只写同步，Agent 不从飞书回读数据）。**未配置时 Agent 自动以网络调研模式运行**，无需任何额外设置。

编辑根目录 `config.yaml` 启用飞书同步：

```yaml
feishu:
  product_obj_token: ""      # 产品数据库 obj_token（仅展示用）
  teardown_obj_token: ""     # 拆机数据库 obj_token
  components_obj_token: ""   # 标准件库 obj_token

local:
  product_csv: ""            # 产品数据库 CSV 路径（填写后可用 import_products.py 导入）
```

> 飞书未配置时，同步操作静默跳过，本地 `data/` 数据不受影响。

### 产品数据库列格式（`data/产品数据库.csv`）

| 列名 | 示例值 |
|------|--------|
| 产品名称 | 石头自清洁扫拖机器人G30S Pro |
| 厂商名称 | Roborock |
| 价格 | 5499 |
| 吸力 | 35000Pa |
| 电池容量 | 6400mAh |
| 续航 | 150分钟 |
| 越障高度 | 越障高度可达 8.8cm |
| 导航方式 | RGB+ToF |
| 是否自清洁 / 拖布抬升 / 自动集尘 ... | 是 / 否 |

### 拆机数据库格式（`data/teardowns/{机型}_teardown.csv`）

| bom_bucket | section | name | model | type | spec | manufacturer | unit_price | qty | confidence | product_source |
|-----------|---------|------|-------|------|------|-------------|-----------|-----|-----------|---------------|
| compute_electronics | PCB | CPU | MR813 | | | MediaTek | 18.0 | 1 | teardown | 石头G30SPro |
| power_motion | 电机 | 驱动轮电机 | | 直流有刷 | | | 8.5 | 2 | web | 石头G30SPro |
| perception | 传感器 | 雷达 | | 激光雷达 | | | | 1 | fcc | 石头G30SPro |

---

## 核心流程：BOM 成本分析（7步）

当用户发送 **"[品牌][型号]，分析 BOM 成本"** 时，Agent 自动执行：

| 步骤 | 动作 | 工具 |
|------|------|------|
| 1 查库 | 检索产品数据库 + 拆机数据库，确认已有数据与缺口 | `get_product_detail` · `get_missing_data` |
| 2 网络检索 | web_search 补全规格层（吸力 / 续航 / 功能布尔值等） | `crawl_product_specs` → `web_fetch` · `web_search` |
| 3 写入数据库 | 规格持久化到 `products_db.json`；同时运行 4-Stage Pipeline 生成拆机 CSV | `save_product` · `generate_teardown_csv` |
| 4 技术亮点 | 列出 3–5 个核心技术差异点 | — |
| 5 BOM 估算 | 8桶结构成本预估表（有拆机数据的桶优先使用实测值） | `generate_bom_estimate` |
| 6 供应链分析 | 核心件供应商 + 降级替代 + 节省金额 + 专利风险 | `match_bom_to_library` |
| 7 差异分析 | vs 数据库中定位相近产品 2–3 个关键差异 | `compare_by_spec` |

### 拆机 CSV 生成 Pipeline（Step 3 内部）

`generate_teardown_csv` 工具内部执行 4 个阶段：

| Stage | 职责 | 说明 |
|-------|------|------|
| 1 Discovery | 多源调研，爬取元器件型号 + 判断置信度 | MyFixGuide → 知乎 → 蓝牙SIG |
| 2 Heuristic Enrichment | SoC 推导伴随件 | 识别到 RK3566/RK3588S 等自动补充 PMIC/RAM/ROM |
| 3 Price Lookup | 查表定价（不调用 API） | `components_lib.csv`（权威）→ `standard_parts.json`（基准 fallback） |
| 4 Aggregate & Audit | 8桶汇总 + ±5% 偏差告警 | 标注超出理论区间的桶，提示人工核实 |

> **价格维护入口**：`data/lib/components_lib.csv`（`cost_min` / `cost_max` 列）。更新后无需重启，下次生成拆机 CSV 时自动生效。

### FCC 数据采集（独立前置步骤，可选）

FCC 采集模块与 BOM 分析流程完全解耦，作为拆机报告的补充内容单独运行：

```bash
# 采集指定机型的 FCC 内部照片，识别 PCB 芯片
python scripts/fetch_fcc.py "石头G30S Pro"

# 直接指定 FCC ID（跳过品牌列表搜索）
python scripts/fetch_fcc.py "科沃斯X8 Pro" --fcc-id 2A6HE-DEX8PRO

# 强制重新抓取（忽略已有缓存）
python scripts/fetch_fcc.py "石头P20 Ultra Plus" --force

# 仅下载 PDF，不做 OCR 识别
python scripts/fetch_fcc.py "石头S91COP02" --download-only
```

输出保存至 `data/teardowns/fcc/{slug}/latest.json`，PDF 原文件保存至 `data/teardowns/fcc/{slug}/pdfs/`。FCC 数据与 `gen_teardown.py` 完全解耦，作为独立的拆机参考资料维护。

**支持品牌**：石头（Roborock）· 追觅（Dreame）· 科沃斯（Ecovacs）· 云鲸（Narwal）· 卧安/SwitchBot · 杉川/3irobotics · 安克/Eufy · 小米 · iRobot

### BOM 8桶成本框架

| # | 桶 | 核心内容 | 旗舰机基准占比 |
|---|----|---------|----|
| 1 | 算力与电子 | SoC · MCU · Wi-Fi/BT · PMIC · RAM/ROM · 被动元件 | ~11% |
| 2 | 感知系统 | LDS/dToF · 结构光摄像头 · IMU · 传感器模组 | ~11% |
| 3 | 动力与驱动 | 风机 · 驱动轮电机 · 底盘升降机构 | ~10% |
| 4 | 清洁功能 | 拖布驱动 · 水泵 · 水箱 · 边刷 · 滚刷 | ~14% |
| 5 | 基站系统 | 集尘泵 · 加热板 · 水路 · 基站电控/结构 | ~22% ¹ |
| 6 | 能源系统 | 电芯 · BMS 保护板 · 充电/配电电路 | ~8% |
| 7 | 整机结构 CMF | 外壳注塑 · 喷涂工艺 · 模具摊销 · 紧固件 | ~11% |
| 8 | MVA + 软件授权 | 组装人工 · 算法版税 (AI避障/SLAM) · OS授权 · 包材 | ~13% |

整机 BOM 率：旗舰机约 **48–55%**（零售价）。

> ¹ 入门机（<¥2000）~7%；中档机（¥2000–4000）~15%；旗舰机（≥¥4000）~22%。

---

## 使用示例

**BOM 完整分析**
> 石头 G30S Pro，分析 BOM 成本

→ 7 步自动执行，输出：8 桶成本拆解 + 拆机 CSV + 供应链替代方案 + 竞品差异

**零部件跨产品查询**
> 越障 4cm 的产品用了哪些驱动轮电机？

→ 返回匹配产品列表及电机型号 / 厂商对比

**降本空间分析**
> 石头 G20S，哪些件是溢价件，降本空间在哪里？

→ 匹配标准件库，给出替代方案和节省金额估算

**子系统横向对比**
> 对比科沃斯 X8 Pro 和石头 S8 MaxV Ultra 的基站系统成本

→ 逐子模组拆解，标注差异件与成本差距

**数据库直查**
> 列出所有拆机数据中出现过的 CPU 型号

→ 从拆机库提取，标注对应机型与置信度

---

## 数据持久化

| 目录 / 文件 | 内容 | 维护方式 |
|------------|------|--------|
| `data/products/products.csv` | 产品规格输入源 | 人工维护 → `import_products.py` 导入 |
| `data/products/products_db.json` | 产品数据库运行时缓存 | Agent 读写，飞书只写镜像 |
| `data/teardowns/{机型}_teardown.csv` | 各机型拆机数据 | `gen_teardown.py` 生成，人工核准入库 |
| `data/teardowns/fcc/{slug}/latest.json` | FCC PCB 芯片识别结果 | `fetch_fcc.py` 生成，独立于 BOM 流程 |
| `data/teardowns/fcc/{slug}/pdfs/` | FCC 原始 PDF 文档 | `fetch_fcc.py --download-only` 下载 |
| `data/lib/components_lib.csv` | 标准件库 + 价格（权威来源） | 人工维护 `cost_min`/`cost_max` |
| `data/lib/standard_parts.json` | 通用物料基准价（fallback） | 人工维护，供未收录件使用 |
| `data/lib/model_aliases.json` | 国内/海外型号映射 | 人工维护（Roborock/Dreame/Ecovacs/Narwal） |

---

## 数据来源与置信度

| 来源 | `bom_source` 标注 | 适用层级 |
|------|------|------|
| 产品数据库（人工维护，CSV 导入） | `database` | 规格 / 价格 / 功能，置信度最高 |
| 实物拆机（teardown CSV） | `teardown` | PCB 芯片 / 电机 / 传感器 |
| `fetch_fcc.py` FCC 照片识别（独立运行） | `fcc` | PCB 芯片，独立维护，不参与 BOM 生成流程 |
| 网络调研 | `web` | 规格层（吸力 / 续航 / 功能布尔值） |
| 行业基准估算 | `estimate` | BOM 成本（无拆机数据时） |

> PCB 级芯片型号通常无法从公开渠道获取，标注 `confidence: inferred` 的数据为同平台推断，需实物拆机核实后才能升级为 `confirmed`。
