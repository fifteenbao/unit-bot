# unit-bot — 扫地机器人 BOM 成本分析 & 技术选型 Agent

行业分析工具，帮助进行扫地机器人（RVC）的 BOM 成本拆解、技术选型对比和竞品分析。

支持作为 **OpenClaw skill** 一键安装，接入飞书 / Slack / WhatsApp / Telegram / Discord 等任意频道使用。

---

## 使用示例

### BOM 完整分析

> 石头 G30S Pro，分析 BOM 成本

自动执行 7 步流程，输出：
- 核心技术亮点（差异化件清单）
- 8 桶 BOM 成本拆解表（含各桶估算金额与零售价占比）
- 拆机 BOM CSV（`data/teardowns/{机型}_teardown.csv`）
- 供应链分析：核心件供应商 + 可降级替代方案 + 节省金额
- 竞品差异：vs 同价位产品 2–3 个关键成本分歧点

### 零部件跨产品查询

> 越障 4cm 的产品用了哪些驱动轮电机？

返回匹配产品列表，附驱动轮电机型号 / 厂商 / 出现频次对比表。

### 降本空间分析

> 石头 G20S，哪些件是溢价件，降本空间在哪里？

匹配标准件库，识别溢价件，给出替代方案与可节省金额估算。

### 子系统横向对比

> 对比科沃斯 X8 Pro 和石头 S8 MaxV Ultra 的基站系统成本

逐子模组拆解，标注差异件与成本差距。

### 数据库直查

> 列出所有拆机数据中出现过的 CPU 型号

从拆机数据库提取，注明对应机型与出处置信度（`teardown` / `fcc` / `web` / `estimate`）。

---

## 安装（OpenClaw）

确保已安装并配置好 [OpenClaw](https://openclaw.ai)，然后：

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

安装完成后在任意已连接的频道发送消息即可，**无需配置 API Key**。

> OpenClaw 会自动安装 Python 依赖并启动本地 webhook 服务（端口 8090，建议配置 `OPENCLAW_WEBHOOK_SECRET` 防止局域网未授权访问）。

---

## 数据库配置（可选）

**所有数据默认保存在本地 `data/` 目录**，飞书仅作为前端展示层（只写同步，不回读）。未配置飞书时一切正常运行。

编辑 `config.yaml` 启用飞书同步：

```yaml
feishu:
  product_obj_token: ""      # 产品数据库 obj_token（仅展示用）
  teardown_obj_token: ""     # 拆机数据库 obj_token
  components_obj_token: ""   # 标准件库 obj_token

local:
  product_csv: ""            # 产品数据库 CSV 路径（填写后可用 import_products.py 导入）
```

> `obj_token` 即多维表格的 `app_token`。若表格嵌入在飞书知识库（Wiki）中，需先从 Wiki 链接解析出 `obj_token`。

> `config.yaml` 已加入 `.gitignore`，不会提交到仓库。

---

## 项目结构

```
unit-bot/
├── SKILL.md                  # OpenClaw skill 元数据与配置说明
├── openclaw_bot.py           # Webhook 服务器（/hooks/agent，端口 8090）
├── agent.py                  # BOM Agent 主逻辑（Claude 工具调用循环）
│
├── core/                     # 运行时库（被 agent.py 直接调用）
│   ├── config.py             # 配置加载（config.yaml → 函数接口）
│   ├── db.py                 # 产品数据库读写（products_db.json，深度合并）
│   ├── bom_loader.py         # 拆机数据只读（data/teardowns/*.csv）
│   ├── components_lib.py     # 标准件库读写（data/lib/components_lib.csv）
│   ├── model_aliases.py      # 国内/海外型号双向模糊匹配（FCC 搜索用）
│   └── feishu_sync.py        # 飞书只写同步（本地写完后单向推送，未配置时跳过）
│
├── scripts/                  # 离线数据维护工具（手动运行，不被 agent 调用）
│   ├── gen_teardown.py       # 生成拆机 CSV（4-Stage Pipeline，需人工核准）
│   ├── build_components.py   # 重建标准件库（teardown CSV → components_lib.csv）
│   └── import_products.py    # 批量导入产品数据（CSV → products_db.json）
│
├── config.yaml               # 数据源配置（飞书 obj_token / 本地路径，不入 git）
├── data/
│   ├── 产品数据库.csv          # 产品规格输入源（人工维护，固定列格式）
│   ├── model_aliases.json    # 国内/海外型号映射表（Roborock/Dreame/Ecovacs/Narwal）
│   ├── standard_parts.json   # 通用物料基准价库（price_1k + discount_factor）
│   ├── products_db.json      # 产品数据库运行时缓存（import_products.py 写入，Agent 读写）
│   ├── teardowns/            # 各机型拆机 CSV（gen_teardown.py 输出，人工核准后入库）
│   │   └── {机型}_teardown.csv
│   └── lib/
│       └── components_lib.csv  # 标准件库（8桶分类，价格权威来源）
└── requirements.txt
```

---

## 数据流

```
人工维护
  data/产品数据库.csv  ──→  import_products.py  ──→  data/products_db.json
                                                           ↕  Agent 实时读写
                                                      飞书产品数据库（只写推送）

拆机数据生成（AI 辅助，含 fccid.io）
  scripts/gen_teardown.py "机型名"          ← 4-Stage Pipeline
    Stage 1  多源 Discovery（FCC/MyFixGuide/知乎）→ 爬元器件型号 + 判 confidence
    Stage 2  Heuristic Enrichment（SoC 推导 PMIC/RAM/ROM 伴随件）
    Stage 3  Price Lookup（components_lib.csv → standard_parts.json，纯查表）
    Stage 4  Aggregate & Audit（8桶汇总，±5% 偏差告警）
    └──→  data/teardowns/{机型}_teardown.csv
  人工核准后 ──→  scripts/build_components.py  ──→  data/lib/components_lib.csv

价格维护
  data/lib/components_lib.csv  ← 人工更新 cost_min / cost_max
    ↑ gen_teardown.py Stage 3 优先读取此文件查价
    ↑ standard_parts.json 作为未收录件的基准 fallback
```

数据置信度：`database`（人工维护）> `teardown` / `fcc`（拆机/照片识别）> `web`（网络调研）> `estimate`（行业基准）

---

## BOM 成本分析框架（8桶）

| # | 子系统 | 核心内容 | 旗舰机基准占比 |
|---|--------|---------|-------------|
| 1 | **算力与电子** | SoC 主板 · Wi-Fi/蓝牙模组 · 被动元件 | ~11% |
| 2 | **感知系统** | LDS/dToF · 视觉摄像头 · IMU · 超声波 | ~11% |
| 3 | **动力与驱动** | 吸尘风机 · 驱动轮模组 · 底盘升降 | ~10% |
| 4 | **清洁功能** | 拖布驱动 · 水泵 · 水箱 · 边刷 · 滚刷 | ~14% |
| 5 | **基站系统** | 集尘 · 水路 · 加热 · 基站电控 · 基站结构 | ~22% ¹ |
| 6 | **能源系统** | 电芯 · BMS · 充电电控 | ~8% |
| 7 | **整机结构 CMF** | 外壳注塑 · 喷涂/IMD · 模具摊销 | ~11% |
| 8 | **MVA + 软件授权** | 组装/测试人工 · 算法版税 · OS 授权 · 包材 | ~13% |

整机 BOM 率参考：旗舰机约 **48–55%**（零售价）。

> ¹ 基站系统占比随档位差异显著：入门机（<¥2000，仅充电+集尘）**~7%**；中档机（¥2000–4000，自清洁+水路）**~15%**；旗舰机（≥¥4000，加热/烘干/多泵）**~22%**。
