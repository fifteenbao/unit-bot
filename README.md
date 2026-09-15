# PLANTS · 通用价值工程项目

本仓库以 **PLANTS** 为通用项目入口：用 PLANS 五阶段把实体产品的事实研究、精益设计、价值裁剪、创新搜索和体系建设串成一条可追溯流程。

PLANTS 是项目名称；**PLANS 是方法论**：

`P 现状研究 → L 精益设计 → A 先进裁剪 → N 价值创新 → S 体系建设`

通用实现位于 [plants/](plants/)，不绑定某个模型、行业或成本分类。它提供：

- 12 个职责清晰的阶段角色和依赖编排；
- ChatGPT、Codex、Claude、OpenClaw 或自建 Agent 可使用的任务包接口；
- 证据引用、输入指纹、结果校验、状态管理和 Markdown 报告；
- `should_cost`、`assembly`、`roi`、`commonality` 等确定性计算合同；
- 按项目隔离的配置、资料和阶段输出。

## 快速开始

```bash
cd plants
python3 agent.py --project examples/project.json /plans status
python3 agent.py --project examples/project.json prepare research > /tmp/plants-task.json
```

将任务包交给 ChatGPT、Codex、Claude 或其他智能体，要求它依据 `instructions` 和项目资料完成阶段并返回结果 JSON，然后导入：

```bash
python3 agent.py --project examples/project.json accept research /tmp/plants-result.json
python3 agent.py --project examples/project.json /plans status
```

也可以接入自建运行器批量执行：

```bash
python3 agent.py --project examples/project.json \
  --runner 'python3 /path/to/runner.py' /plans
```

新用户指南、具体“机电泵降本”案例、配置格式和应用接入方式见 [plants/README.md](plants/README.md)。

## PLANS 方法论原文

完整的阶段定义、方法和依赖关系见 [PLANS 价值设计流程.md](PLANS%20价值设计流程.md)。

## 行业案例：扫地机器人

扫地机器人是本仓库最初的行业实现。其 7 桶成本框架、FCC/OCR 采集、产品别名、供应商库和默认工艺数据只适用于该行业，已单独整理为 [扫地机器人 PLANS 案例](plants/docs/cases/robot-vacuum.md)。

原行业实现仍保留在 `agent.py`、`agents/`、`core/` 和 `scripts/`，用于兼容已有项目；新项目应优先从 `plants/` 开始。

## 目录结构

```text
plants/
├── agent.py              # 通用 CLI / 交互入口
├── core/                 # 编排、校验和确定性计算
├── agents/               # PLANS 12 个阶段的注册表与提示词
├── examples/             # 通用项目示例
├── tests/                # 独立运行测试
└── docs/                 # 架构与行业案例
```

## 验证

```bash
cd plants
python3 -m unittest discover -s tests -v
```

当前核心只负责格式、身份、依赖和证据引用校验；`complete` 不代表事实、成本、专利或安全结论已经由工程师确认。
