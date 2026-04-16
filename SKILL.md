---
name: unit-bot
description: 扫地机器人 BOM 成本分析与技术选型专家。当用户询问扫地机器人（robot vacuum）的 BOM 成本、技术选型、零部件对比、供应链分析、竞品拆解时使用此技能。支持自动网络调研新产品并写入本地数据库。
version: 1.0.0
homepage: https://github.com/fifteenbao/unit-bot
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3", "pip3"]}, "emoji": "🤖", "os": ["darwin", "linux"], "forwardPort": 8090, "forwardPath": "/hooks/agent"}}
---

# unit-bot — 扫地机器人 BOM 成本分析与技术选型

## 能力范围

- **产品数据库**：查询已收录产品的技术规格、BOM 成本、电机 / 传感器 / PCB 芯片清单
- **标准件库**：浏览 41 个 2026 年主流旗舰件，覆盖导航 / 感知 / 动力 / 清洁 / 续航 / 基站 / CMF / 包装 8 个硬件层
- **自动调研新产品**：说出产品名，Agent 自动 web_search → 整理数据 → 写入数据库 → 输出 BOM 估算
- **降本分析**：溢价件识别、可替代方案、专利风险评估
- **竞品对比**：多产品横向规格 / 成本对比

## 使用示例

```
帮我添加 [品牌][型号]，分析 BOM 成本
越障 4cm 的产品用了哪些驱动轮电机？
[产品名] 的降本空间在哪里？
对比 [产品A] 和 [产品B] 的基站系统成本
```

## 数据持久化

产品数据库和标准件库保存在本地 `data/` 目录，重启后数据不丢失。
