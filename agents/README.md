# PLANS 12 子 agent 集合

每个子 agent 对应价值设计流程 PLANS 的一个具体角色（不是整个阶段）。主 agent ([agent.py](../agent.py)) 通过 `from agents import <stage_key>` 调度。

> 文档来源：[价值设计流程PLANS.md](../价值设计流程PLANS.md)

## 目录结构

```
agents/
├── README.md          # 你正在看
├── base.py            # 子 agent 公共运行时 (run_subagent + JSON 抽取)
│
├── p_research/        # P · 产品研究员    /research
├── p_teardown/        # P · 拆解分析师    /teardown
├── p_issues/          # P · 问题诊断师    /issues
│
├── l_dfa/             # L · DFA 优化师     /dfa
├── l_dfm/             # L · DFM 优化师     /dfm  (含 Should Cost)
│
├── a_function/        # A · 功能建模师    /function  (TRIZ)
├── a_trim/            # A · 裁剪策略师    /trim      (TRIZ 矛盾矩阵)
│
├── n_fos/             # N · 功能创新搜索师  /fos
├── n_patent/          # N · 专利规避师    /patent    ⚠️ 非法律意见
├── n_trend/           # N · 趋势分析师    /trend     (S 曲线, 独立可跑)
│
├── s_platform/        # S · 平台架构师    /platform
└── s_costsystem/      # S · 成本体系构建师  /costsystem
```

## 12 子 agent 一览

| Stage Key | 阶段 | Agent 角色 | 命令 | 工具数 | 上游依赖 |
|-----------|------|----------|------|--------|---------|
| `p_research` | P | 产品研究员 | `/research` | 8 | — |
| `p_teardown` | P | 拆解分析师 | `/teardown` | 8 | — |
| `p_issues` | P | 问题诊断师 | `/issues` | 4 | — |
| `l_dfa` | L | DFA 优化师 | `/dfa` | 10 | `p_teardown` + `p_issues` |
| `l_dfm` | L | DFM 优化师 (Should Cost) | `/dfm` | 14 | `p_teardown` |
| `a_function` | A | 功能建模师 (TRIZ) | `/function` | 10 | `l_dfa` + `l_dfm` |
| `a_trim` | A | 裁剪策略师 (TRIZ 矛盾) | `/trim` | 11 | `a_function` |
| `n_fos` | N | 功能创新搜索师 (FOS) | `/fos` | 10 | `a_trim` |
| `n_patent` | N | 专利规避师 | `/patent` | 4 | `n_fos` |
| `n_trend` | N | 趋势分析师 (S 曲线) | `/trend` | 8 | — |
| `s_platform` | S | 平台架构师 | `/platform` | 8 | `a_trim` + `n_fos` |
| `s_costsystem` | S | 成本体系构建师 | `/costsystem` | 7 | `a_trim` + `n_fos` |

阶段依赖在 [`core/plans_store.py`](../core/plans_store.py) 的 `STAGE_DEPS` 集中维护；运行时若依赖未满足，主 agent 返回 `status: blocked` + `missing_prereqs`，提示用户先跑前置阶段。

## 每个子 agent 的内部结构

每个 `<stage_key>/` 子目录都遵循同样的 5 文件约定：

```
<stage_key>/
├── __init__.py        # 导出 STAGE / STAGE_TITLE / SYSTEM_PROMPT / ALLOWED_TOOLS / render_md / build_user_input
├── prompt.md          # system prompt（独立 markdown，便于阅读和修改）
├── tools.py           # ALLOWED_TOOLS — 该 agent 允许调用的工具白名单
├── schema.py          # build_user_input(product_key) + 输出 JSON schema 文档
└── render.py          # render_md(product_key, stage_title, data) — JSON → markdown 报告
```

### 一眼看懂某个 agent 在做什么

```bash
# 想知道 /research 调研什么 → 直接读 prompt
cat agents/p_research/prompt.md

# 想知道 /dfa 能调什么工具 → 看白名单
cat agents/l_dfa/tools.py

# 想知道 /trim 产出什么字段 → 看 schema 文档
cat agents/a_trim/schema.py

# 想知道 /fos 报告长什么样 → 看 render
cat agents/n_fos/render.py
```

## 工作流：阶段依赖图

```
P 阶段（无依赖，可并行）
  /research ──┐
  /teardown ──┼─→ L 阶段
  /issues ────┘    /dfa (上游: /teardown + /issues)
                   /dfm (上游: /teardown)
                            │
                            ▼
                   A 阶段
                     /function (上游: /dfa + /dfm)
                            │
                            ▼
                     /trim (上游: /function)
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
            N 阶段        S 阶段          (独立 N 阶段)
              /fos          /platform      /trend
              ▼             /costsystem
              /patent
```

## 加新阶段 / 改现有阶段的工作流

### 改 prompt（最常见）
直接编辑 `<stage_key>/prompt.md`。改动后 `git diff` 只显示 prompt 变化，干净清晰。

### 加/减允许的工具
编辑 `<stage_key>/tools.py` 的 `ALLOWED_TOOLS` 列表。注意：工具名必须是主 agent [`CLIENT_TOOLS`](../agent.py) 里已存在的工具，否则该工具调用会失败。

### 改输出 schema
1. 编辑 `<stage_key>/schema.py` 的 `OUTPUT_SCHEMA_DOC`（人类参考）。
2. 同步更新 `<stage_key>/prompt.md` 末尾的 ```json 示例（LLM 实际遵循的就是这个）。
3. 编辑 `<stage_key>/render.py` 让 `render_md` 处理新字段。

### 加新阶段
1. 在 [`core/plans_store.py`](../core/plans_store.py)：
   - `STAGES` 元组加新 stage key
   - `STAGE_TITLES` 加标题
   - `STAGE_PHASE` 标明属 P/L/A/N/S 哪个大阶段
   - `STAGE_DEPS` 声明依赖
2. 复制任一现有 `<stage_key>/` 子目录改名，按 5 文件约定填内容。
3. 在 [`agent.py`](../agent.py)：
   - `_stage_module()` 字典加新映射
   - `_STAGE_TO_COMMAND` 字典加命令名映射
   - 新增 `tool_plans_<command>` 包装函数
   - `CLIENT_TOOLS` 加 schema
   - `CLIENT_DISPATCH` 加 dispatch 入口
   - `SYSTEM_PROMPT` 在阶段表里登记
   - `WELCOME` 横幅加一行

## 子 agent 公共约定

- **只读不写业务库**：子 agent 不调用 `save_product` / `update_spec` / `upsert_component` 等写操作。所有写库由主 agent 在收到 JSON 后通过 `plans_store.save_stage()` 统一执行。
- **输出格式**：必须以一段 ```json 代码块结束。`base.py` 的 `extract_json` 会优先从 ```json``` 块解析，失败则尝试整段文本里的最大花括号对象。
- **失败兜底**：若子 agent 没返回有效 JSON，主 agent 返回 `status: error`，不污染 plans_db.json。
- **OpenClaw 兼容**：`web_search` / `web_fetch` 是 Anthropic 服务端工具，OpenClaw 后端会自动剔除（在 [`agent.py`](../agent.py) 的 `_make_client()` 完成）。

## 详细架构

完整设计动机和讨论见 [`docs/agents_architecture.md`](../docs/agents_architecture.md) 和 [价值设计流程PLANS.md](../价值设计流程PLANS.md)。
