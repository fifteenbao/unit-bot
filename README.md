# unit-bot — 扫地机器人 BOM 成本分析 & 技术选型 Agent

行业分析工具，帮助进行扫地机器人（RVC）的 BOM 成本拆解、技术选型对比和竞品分析。

支持作为 **OpenClaw skill** 一键安装，接入飞书 / Slack / WhatsApp / Telegram / Discord 等任意频道使用。

- [ ] 拆机数据库、成本占比优化
- [ ] 动态 VAVE,增加 “成本替换矩阵”
- [ ] CMF 与加工费（MVA）的量化公式,基于克重的成本估算脚本

---

## 使用示例

### BOM 完整分析

> 石头 G30S Pro，分析 BOM 成本

自动执行 7 步流程，输出：
- 核心技术亮点（差异化件清单）
- 8 桶 BOM 成本拆解表（含各桶估算金额与零售价占比）
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

从拆机数据库提取，注明对应机型与出处置信度（`teardown` / `web` / `estimate`）。

---

## 安装（OpenClaw）

确保已安装并配置好 [OpenClaw](https://openclaw.ai)，然后：

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

安装完成后，首次使用前配置飞书数据库链接（见下方"数据库配置"），然后在任意已连接的频道发送消息即可，**无需配置 API Key**。

> OpenClaw 会自动安装 Python 依赖并启动本地 webhook 服务（端口 8090，建议配置 `OPENCLAW_WEBHOOK_SECRET` 防止局域网未授权访问）。

---

## 数据库配置（首次使用）

编辑 `data/config.yaml`，填写飞书多维表格链接或本地文件路径（二选一，本地文件优先）：

```yaml
feishu:
  product_table_url: "https://your-feishu-domain/base/xxx?table=tbl_product"
  teardown_table_url: "https://your-feishu-domain/base/xxx?table=tbl_teardown"
  components_table_url: "https://your-feishu-domain/base/xxx?table=tbl_components"

local:
  product_xlsx: ""       # 本地产品数据库 xlsx（填写后覆盖飞书）
  teardown_xlsx: ""      # 本地拆机 Excel
```

未配置时以**纯网络调研模式**运行，规格层通过 web_search 获取，PCB/电机级数据标注为 `estimate`。

> `data/config.yaml` 已加入 `.gitignore`，不会提交到仓库。

---

## 手动运行（不使用 OpenClaw）

```bash
git clone https://github.com/fifteenbao/unit-bot
cd unit-bot
pip install -r requirements.txt
cp .env.example .env   # 填写飞书配置

# 启动 webhook 服务
python openclaw_bot.py
```

服务启动后可直接 curl 调用：

```bash
curl -X POST http://localhost:8090/hooks/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "列出所有产品", "sessionId": "test"}'
```

---

## 项目结构

```
unit-bot/
├── SKILL.md                  # OpenClaw skill 清单与配置说明
├── openclaw_bot.py            # Webhook 服务器（/hooks/agent）
├── agent.py                   # BOM Agent 核心逻辑（Claude 工具调用循环）
├── core/
│   ├── config.py              # 数据源配置加载器（config.yaml → 环境变量）
│   ├── db.py                  # 产品数据库 CRUD（深度合并 / 完整度追踪）
│   ├── bom_loader.py          # 拆机 Excel 解析（自动识别 data/ 目录）
│   ├── components_lib.py      # 标准件库 JSON CRUD
│   └── feishu_sync.py         # 飞书多维表格同步（未配置时静默跳过）
├── scripts/
│   ├── gen_teardown.py        # 通用拆机分析 Excel 生成器（含 FCC ID.io + 网络补全）
│   ├── build_components.py    # 拆机 Excel → teardown CSV + 标准件库
│   ├── import_products.py     # 产品数据库 xlsx 批量导入
│   └── start.py               # 服务启动入口
├── config.yaml               # 数据源配置（飞书链接 / 本地路径，不入 git）
├── data/
│   ├── products_db.json        # 产品规格数据库（含 last_updated）
│   ├── teardowns/              # 各机型拆机 CSV
│   │   └── {机型}_teardown.csv
│   ├── lib/
│   │   └── components_lib.csv  # 标准件库（8桶分类，含 last_updated）
│   └── {机型}_拆机分析.xlsx    # gen_teardown.py 输出的分析报告
└── requirements.txt
```

---

## 数据流

```
人工维护
  飞书产品数据库  ──→  import_products.py  ──→  data/products_db.json
  飞书拆机数据库  ──→  build_components.py ──→  data/teardowns/{机型}.csv
                                           ──→  data/lib/components_lib.csv

Agent 自动调研
  web_search  ──→  crawl_product_specs  ──→  save_product  ──→  products_db.json
                                                            ──→  飞书产品数据库（同步）

拆机报告生成（AI 辅助，含 FCC ID.io）
  gen_teardown.py "机型名"
    ├── FCC ID.io 内部照片 / 框图  ──┐
    ├── 拆机报告 / 网络评测        ──┼→  teardowns/{机型}_teardown.csv
    └── 元件价格补全（LCSC/Mouser）──┘
                                      └→  {机型}_拆机分析.xlsx（双Sheet报告）
  人工核准后 ──→  build_components.py  ──→  components_lib.csv
```

数据置信度：`teardown`（FCC照片/实物拆机）> `web`（网络调研）> `estimate`（行业基准推算）

---

## BOM 成本分析框架（8桶）

| # | 子系统 | 核心内容 | 旗舰机基准占比 |
|---|--------|---------|-------------|
| 1 | **算力与电子** | SoC 主板 · Wi-Fi/蓝牙模组 · 被动元件 | 10–12% |
| 2 | **感知系统** | LDS/dToF · 视觉摄像头 · IMU · 超声波 | 10–13% |
| 3 | **动力与驱动** | 吸尘风机 · 驱动轮模组 · 底盘升降 | 10–12% |
| 4 | **清洁功能** | 拖布驱动 · 水泵 · 水箱 · 边刷 · 滚刷 | 13–17% |
| 5 | **基站系统** | 集尘 · 水路 · 加热 · 基站电控 · 基站结构 | 15–20% ¹ |
| 6 | **能源系统** | 电芯 · BMS · 充电电控 | 7–9% |
| 7 | **整机结构 CMF** | 外壳注塑 · 喷涂/IMD · 模具摊销 | 10–13% |
| 8 | **MVA + 软件授权** | 组装/测试人工 · 算法版税 · OS 授权 · 包材 | 9–13% |

整机 BOM 率参考：旗舰机约 **48–55%**（零售价）。

> ¹ 基站系统占比随档位差异显著：入门机（¥2000–2500，仅充电+集尘）**5–8%**；中档机（¥2500–3500，自清洁+水路）**12–15%**；旗舰机（¥5000+，加热/烘干/多泵）**15–20%**。


### 基站系统细化（第 5 桶）

| 子模组 | 核心内容 | 占基站桶比例 |
|--------|---------|------------|
| 集尘模组 | 集尘风机 + 尘袋结构 + HEPA 滤网 | ~30% |
| 水路模组 | 加热板 + 循环水泵 + 管路 + 污水箱 | ~30% |
| 基站电控 | 基站主控板 + 触控屏/LED + 传感器 | ~20% |
| 基站结构 CMF | 外壳注塑 + 喷涂 | ~20% |

### 软件/授权隐形 BOM（第 8 桶）

| 项目 | 单机成本参考 |
|------|------------|
| 导航/SLAM 算法版税 | ¥5–20 |
| 语音/AI 推理授权 | ¥3–10 |
| RTOS / 中间件 | ¥0–5 |
| 云服务摊销 | ¥5–15 |

合计约 **¥15–50 / 台**，旗舰机出厂 BOM 占比约 **0.5–2%**。
