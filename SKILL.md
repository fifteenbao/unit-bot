---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。支持自动网络调研新产品并写入本地数据库。
version: 1.0.0
homepage: https://github.com/fifteenbao/unit-bot
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"], "env": ["ANTHROPIC_API_KEY"]}, "primaryEnv": "ANTHROPIC_API_KEY", "emoji": "🤖", "os": ["darwin", "linux"], "forwardPort": 8090, "forwardPath": "/hooks/agent"}}
---

# BOM Agent — 扫地机器人技术选型与成本分析

## 能力范围

- **产品数据库**：查询已收录产品的技术规格、BOM 成本、电机/传感器/PCB 芯片清单
- **标准件库**：浏览 41 个 2026 年主流旗舰件（导航/感知/动力/清洁/续航/基站/CMF/包装）
- **自动调研新产品**：说出产品名，Agent 自动 web_search → 整理数据 → 写入数据库 → 输出 BOM 估算
- **降本分析**：溢价件识别、可替代方案、专利风险评估
- **竞品对比**：多产品横向规格 / 成本对比

## 启动服务

使用本技能前，确保 BOM Agent 服务在本地运行：

```bash
# 首次安装依赖
pip3 install -r $SKILL_DIR/requirements.txt

# 启动服务（默认端口 8090）
python3 $SKILL_DIR/scripts/start.py
```

或直接运行：

```bash
cd $SKILL_DIR && python3 openclaw_bot.py
```

服务启动后检查健康状态：

```bash
curl http://localhost:8090/health
# 期望: {"status": "ok", "timestamp": ...}
```

## 发送查询

将用户问题 POST 到本地服务：

```bash
curl -s -X POST http://localhost:8090/hooks/agent \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"<用户问题>\", \"sessionId\": \"<对话ID>\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])"
```

**重要**：每轮对话使用相同的 `sessionId`，Agent 会自动维护多轮上下文。

## 使用示例

```
用户: 帮我添加 追觅X40 Ultra，分析 BOM 成本
→ Agent 自动执行 6 步：网络检索 → 写库 → 技术亮点 → BOM 估算 → 供应链 → 竞品差异

用户: 越障 4cm 的产品用了哪些驱动轮电机？
→ 查询产品数据库，返回电机型号 / 厂商对比表

用户: 科沃斯X2pro 的降本空间在哪里？
→ 匹配标准件库，识别溢价件，给出替代方案和节省金额
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API 密钥 |
| `OPENCLAW_WEBHOOK_SECRET` | 可选 | 请求验签密钥 |
| `OPENCLAW_BOT_PORT` | 可选 | 服务端口（默认 8090） |
| `BOM_EXCEL_FILE` | 可选 | 私有拆机 Excel 路径 |

## 数据持久化

产品数据库和标准件库保存在 `data/` 目录下的 JSON 文件，本地持久化，重启服务后数据不丢失。
如配置了飞书多维表格，数据会同步写入 Bitable，支持可视化管控。
