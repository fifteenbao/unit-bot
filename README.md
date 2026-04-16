# 扫地机器人 BOM 成本分析 & 技术选型 Agent

基于 Claude claude-opus-4-6 构建的行业分析工具，帮助进行扫地机器人（RVC）的 BOM 成本拆解、技术选型对比和竞品分析。支持本地 CLI 和飞书机器人两种交互方式，飞书多维表格作为数据库可视化管控界面。

---

## OpenClaw 安装

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

安装后在任意已连接频道（Slack / WhatsApp / Telegram 等）发送消息即可使用，无需额外配置 API Key。

---

## 快速开始

### 飞书机器人部署

```bash
pip install -r requirements.txt
cp .env.example .env        # 填写所有飞书配置项（见下方说明）

# 开发模式
python -m feishu.bot

# 生产模式（需公网 IP 或内网穿透）
gunicorn "feishu.bot:app"
```

### 本地 CLI

```bash
pip install -r requirements.txt
cp .env.example .env        # 填写 ANTHROPIC_API_KEY
python cli.py
```


---

## 飞书配置

### 1. 创建飞书自建应用

1. 进入[飞书开放平台](https://open.feishu.cn) → 创建企业自建应用
2. **应用能力** → 添加「机器人」
3. **权限管理** → 开通以下权限：
   - `im:message`（接收消息）
   - `im:message:send_as_bot`（发送消息）
4. **事件订阅** → 添加事件 `im.message.receive_v1`
5. 事件请求 URL 填写：`https://your-server/webhook/feishu`
6. **凭证与基础信息** 页面复制 App ID / App Secret / Verification Token

### 2. 配置飞书多维表格（Bitable）

创建两张表，字段如下：

**产品表（Products）**

| 字段名 | 类型 |
|--------|------|
| 产品Key | 文本（主键） |
| 品牌 / 型号 | 文本 |
| 零售价(元) | 数字 |
| 上市时间 / 雷达类型 | 文本 |
| 定位 | 单选（旗舰/中高端/入门） |
| 越障高度(cm) / 吸力(Pa) / 电池容量(mAh) | 数字 |
| 拖布升降 | 勾选框 |
| BOM率(%) | 数字 |
| 数据完整度 | 文本（JSON） |
| 完整JSON数据 | 文本 |

**标准件表（Components）**

| 字段名 | 类型 |
|--------|------|
| 件ID / 名称 | 文本 |
| 分类 | 单选 |
| 档次 | 单选（溢价/主流/减配） |
| 成本区间(元) | 文本 |
| 专利风险 | 单选（low/medium/high） |
| 主要供应商 | 文本 |
| 完整JSON数据 | 文本 |

打开多维表格，URL 中的 `{APP_TOKEN}` 即为 `FEISHU_BITABLE_APP_TOKEN`，各表的 Table ID 在「字段配置 → 高级设置」中查看。

### 3. 填写 `.env`

```ini
ANTHROPIC_API_KEY=sk-ant-...

FEISHU_APP_ID=cli_...
FEISHU_APP_SECRET=...
FEISHU_VERIFICATION_TOKEN=...
FEISHU_ENCRYPT_KEY=          # 未开启消息加密留空

FEISHU_BITABLE_APP_TOKEN=R...B
FEISHU_PRODUCTS_TABLE_ID=tbl...
FEISHU_COMPONENTS_TABLE_ID=tbl...

BOT_HOST=0.0.0.0
BOT_PORT=8080
```

### 4. 首次同步数据到 Bitable

服务启动后调用：

```bash
curl -X POST http://localhost:8080/sync/bitable
```

---

## 项目结构

```
bom_agent/
├── agent.py                    # Agent 主逻辑（Claude 工具调用循环）
├── cli.py                      # 本地 CLI 入口
├── .env.example                # 环境变量模板
├── requirements.txt
│
├── core/                       # 核心数据层
│   ├── db.py                   # 产品数据库 CRUD（深度合并/完整度追踪）
│   ├── components_lib.py       # 标准件库 CRUD + 41 个初始标准件
│   └── bom_loader.py           # Excel 拆机数据解析
│
├── feishu/                     # 飞书集成
│   ├── config.py               # 从 .env 读取飞书配置
│   ├── client.py               # 飞书 API 客户端（消息/卡片/Bitable CRUD）
│   ├── bitable.py              # Bitable 数据同步适配器
│   └── bot.py                  # Flask Webhook 服务器
│
└── data/                       # 数据文件（自动生成/更新）
    ├── products_db.json        # 产品数据库
    ├── components_lib.json     # 标准件库
    └──product_specs.json      # 旧格式规格数据（迁移备份）
```


## Agent 工具列表

### 产品数据库

| 工具 | 说明 |
|------|------|
| `list_products` | 列出所有产品概要 |
| `get_product_detail` | 获取单产品完整信息 |
| `get_motors` / `get_sensors` / `get_pcb_components` | 获取电机/传感器/芯片清单 |
| `get_bom_cost` | 获取 7 桶 BOM 成本结构 |
| `search_by_spec` | 按规格筛选产品（支持 `>=` / `<=` / `>` / `<`） |
| `compare_by_spec` | 横向对比指定类别 |
| `get_missing_data` | 列出数据缺口 |
| `save_product` | 新建或更新产品（深度合并） |
| `update_spec` / `update_bom_cost` | 更新单个字段 |
| `generate_bom_estimate` | 按 7 桶基准比例估算 BOM 成本 |
| `delete_product` | 删除产品 |

### 标准件库

| 工具 | 说明 |
|------|------|
| `list_components` | 按分类/档次/关键词浏览 |
| `get_component` | 获取单件完整详情 |
| `save_component` | 新增或更新标准件 |
| `delete_component` | 删除标准件 |
| `match_bom_to_library` | 产品 × 标准件库交叉对比，识别溢价/主流/减配 |
| `compare_cost_benchmark` | 各子系统 BOM 与库基准对比 |

### 网络调研

| 工具 | 说明 |
|------|------|
| `web_search` | 搜索产品规格、拆机报告、供应商信息 |
| `web_fetch` | 抓取指定页面 |

---

## BOM 成本 7 桶结构

| 桶 | 说明 | 占比基准 |
|----|------|--------|
| 感知与控制 | 主板+摄像头+LDS/dToF | 18% |
| 动力系统 | 吸尘风机+驱动轮模组 | 10% |
| 清洁模组 | 拖布/履带+泵+水箱 | 15% |
| 电池动力 | 电芯+BMS | 7% |
| 基站系统 | 加热+电解水+水路+集尘+触控 | 35% |
| 机身结构CMF | 外壳+注塑+喷涂+滚刷 | 10% |
| 包装耗材 | 尘袋+滤网+包材 | 5% |

整机 BOM 率参考：旗舰机约 48–55%（零售价）。

---

## 数据完整度

产品数据分 5 个维度自动打分（complete / partial / missing）：

| 维度 | 关键字段 |
|------|----------|
| basic_specs | 越障高度、吸力、拖布升降、雷达类型、电池容量 |
| bom_cost | 7 桶 BOM 成本、总成本 |
| motors | 电机清单 |
| sensors | 传感器清单 |
| pcb | PCB 芯片清单 |
