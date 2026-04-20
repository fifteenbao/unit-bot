---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"], "forwardPort": 8090, "forwardPath": "/hooks/agent"}}
---

# unit-bot — 扫地机器人 BOM 成本分析与技术选型

## 数据库配置（可选）

编辑根目录 `config.yaml`，填写飞书多维表格链接。**未配置时 Agent 自动以网络调研模式运行**，无需任何额外设置。

```yaml
feishu:
  app_id: ""        # 飞书开放平台 App ID（同步写回时必填）
  app_secret: ""    # 飞书开放平台 App Secret

  # 支持 /base/ 直链或 /wiki/ 格式，wiki 格式需填写 app_id/app_secret 自动解析
  product_table_url: "https://your-domain.feishu.cn/wiki/xxx"
  teardown_table_url: "https://your-domain.feishu.cn/wiki/xxx"
  components_table_url: ""

local:
  product_xlsx: ""    # 本地产品数据库 xlsx（优先级高于飞书）
  teardown_xlsx: ""   # 本地拆机 Excel
```

> 飞书链接未配置或凭证缺失时，同步操作静默跳过，本地 `data/` 数据不受影响。

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

**拆机数据库** — 每个 Sheet 对应一款产品：

```
A列（合并）  B列（类别）   C列（功能/名称）  D列（型号）  E列（数量）...
PCB          主板          CPU               MR813        1
             （merged）    RAM               GDQ2BFAA     2
电机         （merged）    驱动轮电机        直流有刷     2
传感器       （merged）    雷达              激光雷达     1
其他         （merged）    电池包            18650 4串2并 1
```

---

## 核心流程：BOM 成本分析（7步）

当用户发送 **"[品牌][型号]，分析 BOM 成本"** 时，Agent 自动执行：

| 步骤 | 动作 | 工具 |
|------|------|------|
| 1 查库 | 检索产品数据库 + 拆机数据库，确认已有数据与缺口 | `get_product_detail` · `get_missing_data` |
| 2 网络检索 | 补全缺失规格（规格层） | `crawl_product_specs` → `web_search` |
| 3 写入数据库 | 持久化，标注 bom_source | `save_product` |
| 4 技术亮点 | 列出 3–5 个核心技术差异点 | — |
| 5 BOM 估算 | 8桶结构成本预估表 | `generate_bom_estimate` |
| 6 供应链分析 | 核心件供应商 + 降级替代 + 节省金额 | `match_bom_to_library` |
| 7 差异分析 | vs 数据库中定位相近产品 2–3 个关键差异 | `compare_by_spec` |

### BOM 8桶成本框架

| # | 桶 | 核心内容 | 旗舰机基准占比 |
|---|----|---------|----|
| 1 | 算力与电子 | SoC 主板 · MCU · Wi-Fi · 被动元件 | 10–12% |
| 2 | 感知系统 | LDS/dToF · 结构光摄像头 · IMU · 超声波 | 10–13% |
| 3 | 动力与驱动 | 吸尘风机 · 驱动轮电机 · 底盘升降 | 10–12% |
| 4 | 清洁功能 | 拖布驱动 · 水泵 · 水箱 · 边刷 · 滚刷 | 13–17% |
| 5 | 基站系统 | 集尘 · 水路 · 加热板 · 基站电控 · 基站结构 | 15–20% ¹ |
| 6 | 能源系统 | 电芯 · BMS · 充电 IC | 7–9% |
| 7 | 整机结构 CMF | 外壳注塑 · 喷涂 · 模具摊销 | 10–13% |
| 8 | MVA + 软件授权 | 组装人工 · 算法版税 · OS · 包材 | 9–13% |

整机 BOM 率参考：旗舰机约 **48–55%**（零售价）。

> ¹ 基站系统占比随档位差异显著：入门机（¥2000–2500，仅充电+集尘）**5–8%**；中档机（¥2500–3500，自清洁+水路）**12–15%**；旗舰机（¥5000+，加热/烘干/多泵）**15–20%**。

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

---

## 数据持久化

| 目录 / 文件 | 内容 |
|------------|------|
| `config.yaml` | 数据源配置（飞书链接 / 本地路径），不入 git |
| `data/products_db.json` | 产品规格数据库，每条记录含 `last_updated` |
| `data/teardowns/{机型}_teardown.csv` | 各机型拆机数据 |
| `data/{机型}_拆机分析.xlsx` | gen_teardown.py 输出的分析报告 |
| `data/lib/components_lib.csv` | 标准件库（8桶分类），每行含 `last_updated` |

重启服务后数据不丢失。建议定期备份 `data/` 目录，或配置飞书同步作为云端备份。

---

## 数据来源与置信度

| 来源 | `bom_source` 标注 | 适用层级 |
|------|------|------|
| 实物拆机（飞书拆机表 / Excel） | `teardown` | PCB 芯片 / 电机 / 传感器 |
| 网络调研 | `web` | 规格层（吸力 / 续航 / 功能布尔值） |
| 行业基准估算 | `estimate` | BOM 成本（无拆机数据时） |

> PCB 级芯片型号通常无法从公开渠道获取，标注 `confidence: inferred` 的数据为同平台推断，需实物拆机核实后才能升级为 `confirmed`。
