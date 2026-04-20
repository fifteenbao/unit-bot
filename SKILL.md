---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"], "forwardPort": 8090, "forwardPath": "/hooks/agent"}}
---

# unit-bot — 扫地机器人 BOM 成本分析与技术选型

## 数据库配置（可选）

**所有数据默认保存在本地 `data/` 目录**，飞书多维表格仅作为前端展示层（只写同步，Agent 不从飞书回读数据）。**未配置时 Agent 自动以网络调研模式运行**，无需任何额外设置。

编辑根目录 `config.yaml` 启用飞书同步：

```yaml
feishu:
  # obj_token 即多维表格的 app_token
  # 若表格嵌入在飞书知识库（Wiki）中，需先从 Wiki API 响应的 obj_token 字段获取
  product_obj_token: ""
  teardown_obj_token: ""
  components_obj_token: ""

local:
  product_csv: ""     # 产品数据库 CSV 路径（填写后可用 import_products.py 导入）
```

> 飞书未配置时，同步操作静默跳过，本地 `data/` 数据不受影响。

### 飞书表格格式约定

**产品数据库** — 每行一款产品，必要列：

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

**拆机数据库** — 每个机型对应一个 CSV 文件（`data/teardowns/{机型}_teardown.csv`）：

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
| 2 网络检索 | 补全规格层；fccid.io 抓取 PCB 芯片（有收录品牌时） | `crawl_product_specs` → `web_search` · `web_fetch` |
| 3 写入数据库 | 持久化，标注 bom_source | `save_product` |
| 4 技术亮点 | 列出 3–5 个核心技术差异点 | — |
| 5 BOM 估算 | 8桶结构成本预估表 | `generate_bom_estimate` |
| 6 供应链分析 | 核心件供应商 + 降级替代 + 节省金额 | `match_bom_to_library` |
| 7 差异分析 | vs 数据库中定位相近产品 2–3 个关键差异 | `compare_by_spec` |

### BOM 8桶成本框架

| # | 桶 | 核心内容 | 旗舰机基准占比 |
|---|----|---------|----|
| 1 | 算力与电子 | SoC 主板 · MCU · Wi-Fi · 被动元件 | ~11% |
| 2 | 感知系统 | LDS/dToF · 结构光摄像头 · IMU · 超声波 | ~11% |
| 3 | 动力与驱动 | 吸尘风机 · 驱动轮电机 · 底盘升降 | ~10% |
| 4 | 清洁功能 | 拖布驱动 · 水泵 · 水箱 · 边刷 · 滚刷 | ~14% |
| 5 | 基站系统 | 集尘 · 水路 · 加热板 · 基站电控 · 基站结构 | ~22% ¹ |
| 6 | 能源系统 | 电芯 · BMS · 充电 IC | ~8% |
| 7 | 整机结构 CMF | 外壳注塑 · 喷涂 · 模具摊销 | ~11% |
| 8 | MVA + 软件授权 | 组装人工 · 算法版税 · OS · 包材 | ~13% |

整机 BOM 率参考：旗舰机约 **48–55%**（零售价）。

> ¹ 基站系统占比随档位差异显著：入门机（<¥2000，仅充电+集尘）**~7%**；中档机（¥2000–4000，自清洁+水路）**~15%**；旗舰机（≥¥4000，加热/烘干/多泵）**~22%**。

---

## 使用示例

**BOM 完整分析**
> 石头 G30S Pro，分析 BOM 成本

→ 7 步自动执行，输出：8 桶成本拆解 + 供应链替代方案 + 竞品差异

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

所有数据**默认保存在本地 `data/` 目录**，飞书为可选的只写展示层（Agent 写入本地后单向同步，不从飞书回读）。

| 目录 / 文件 | 内容 |
|------------|------|
| `config.yaml` | 数据源配置（飞书 obj_token / 本地路径），不入 git |
| `data/产品数据库.csv` | 产品规格输入源（人工维护，`import_products.py` 读取） |
| `data/products_db.json` | 产品数据库运行时缓存（Agent 读写，飞书只写镜像） |
| `data/teardowns/{机型}_teardown.csv` | 各机型拆机数据（含 confidence 来源标注） |
| `data/lib/components_lib.csv` | 标准件库（8桶分类，`build_components.py` 重建） |

重启服务后数据不丢失。建议定期备份 `data/` 目录；配置飞书同步后可将飞书多维表格用作可视化看板。

---

## 数据来源与置信度

| 来源 | `bom_source` 标注 | 适用层级 |
|------|------|------|
| 产品数据库（人工维护，CSV 导入） | `database` | 规格 / 价格 / 功能，置信度最高 |
| 实物拆机（teardown CSV） | `teardown` | PCB 芯片 / 电机 / 传感器 |
| fccid.io 照片识别 | `fcc` | PCB 芯片（石头 / 追觅 / 科沃斯 / 云鲸） |
| 网络调研 | `web` | 规格层（吸力 / 续航 / 功能布尔值） |
| 行业基准估算 | `estimate` | BOM 成本（无拆机数据时） |

> PCB 级芯片型号通常无法从公开渠道获取，标注 `confidence: inferred` 的数据为同平台推断，需实物拆机核实后才能升级为 `confirmed`。
