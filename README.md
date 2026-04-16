# unit-bot — 扫地机器人 BOM 成本分析 & 技术选型 Agent

行业分析工具，帮助进行扫地机器人（RVC）的 BOM 成本拆解、技术选型对比和竞品分析。

支持作为 **OpenClaw skill** 一键安装，接入 Slack / WhatsApp / Telegram / Discord 等任意频道使用。

---

## 安装（OpenClaw）

确保已安装并配置好 [OpenClaw](https://openclaw.ai)，然后：

```bash
openclaw skills add https://github.com/fifteenbao/unit-bot
```

安装完成后，在任意已连接的频道发送消息即可使用，**无需额外配置 API Key**。

> 首次使用时，OpenClaw 会自动安装 Python 依赖并启动本地 webhook 服务（端口 8090）。

---

## 使用示例

```
帮我添加 [品牌][型号]，分析 BOM 成本
```
→ 自动执行：网络检索 → 写入数据库 → 技术亮点 → BOM 估算 → 供应链分析 → 竞品差异

```
越障 4cm 的产品用了哪些驱动轮电机？
```
→ 查询产品数据库，返回电机型号 / 厂商对比表

```
[产品名] 哪些件是溢价件，降本空间在哪里？
```
→ 匹配标准件库，识别溢价件，给出替代方案和节省金额

```
对比 [产品A] 和 [产品B] 的基站系统成本
```
→ 横向对比指定子系统 BOM 成本

---

## 手动运行（不使用 OpenClaw）

```bash
git clone https://github.com/fifteenbao/unit-bot
cd unit-bot
pip install -r requirements.txt
cp .env.example .env   # 填写 ANTHROPIC_API_KEY

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
├── SKILL.md            # OpenClaw skill 清单
├── openclaw_bot.py     # Webhook 服务器（/hooks/agent）
├── agent.py            # BOM Agent 核心逻辑（Claude 工具调用循环）
├── scripts/
│   └── start.py        # 服务启动入口
├── core/
│   ├── db.py           # 产品数据库 CRUD（深度合并 / 完整度追踪）
│   ├── components_lib.py  # 标准件库 CRUD（41 个初始标准件）
│   └── bom_loader.py   # 拆机 Excel 解析（可选）
├── data/               # 运行时数据（不入 git）
├── .env.example
└── requirements.txt
```

---

## 数据资产

### 产品数据库

内置若干款拆机实测产品数据，覆盖主流旗舰价位段。新产品通过对话自动调研写入，数据本地持久化。

### 标准件库（41 个标准件）

覆盖 2026 年旗舰机 8 个硬件层：导航模组 / 感知与控制 / 动力系统 / 清洁系统 / 续航系统 / 基站系统 / 机身结构CMF / 包装耗材。

每个标准件记录：规格参数、成本区间、主要供应商、专利风险、降级替代方案。

---

## 可选：私有拆机数据

将 `.xlsx` 放入 `data/` 目录（或设置 `BOM_EXCEL_FILE=/path/to/file.xlsx`），Agent 自动加载。格式约定：每个 Sheet 对应一款产品，按「电机 / 传感器 / 其他」分 section。

不提供 Excel 时，系统以纯网络调研模式运行。

---

## BOM 成本 7 桶结构

| 子系统 | 内容 | 基准占比 |
|--------|------|---------|
| 感知与控制 | 主板 + 摄像头 + LDS/dToF | 18% |
| 动力系统 | 吸尘风机 + 驱动轮模组 | 10% |
| 清洁模组 | 拖布 + 泵 + 水箱 | 15% |
| 电池动力 | 电芯 + BMS | 7% |
| 基站系统 | 加热 + 水路 + 集尘 + 触控 | 35% |
| 机身结构CMF | 外壳 + 注塑 + 喷涂 | 10% |
| 包装耗材 | 尘袋 + 滤网 + 包材 | 5% |

整机 BOM 率参考：旗舰机约 **48–55%**（零售价）。
