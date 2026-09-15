# 12 个阶段角色

`registry.json` 是命令、顺序、标题、必需依赖与输出栏目的唯一注册表。
每个 `<stage>/prompt.md` 描述本阶段的通用方法、分析边界及证据要求。
这些角色从 unit-bot 原有 12 个 agent 提取，行业专用工具不属于本通用核心。

## 结果协议

结果必须包含 `packet_id`、`project_id`、`stage`、`summary`、`sections`、`evidence`、`limitations`。
完整模板由 `prepare` 自动生成。`sections` 每个栏目都是对象数组，条目业务字段由阶段任务决定。

```json
{
  "statement": "这一条是待验证的产品定位假设",
  "evidence_ids": ["E1"]
}
```

对应本结果证据条目：

```json
{
  "id": "E1",
  "source": "项目简报 brief.md 第 2 段",
  "claim": "目标用户定义尚待访谈验证",
  "kind": "assumption"
}
```

`kind` 取 `fact`、`inference`、`assumption`。上游引用可用 `upstream.l_dfm.sections.should_cost_analysis[0]` 作为 source。
记录链接、日期、页码或条目定位，保证人能复核。只检查引用是否存在，不自动判断证据是否支持结论。
空栏目用 limitations 说明，不用零值冒充未知。金额字段明确币种、单位和估算口径。

## 维护

- 修改职责：编辑阶段 prompt。
- 修改输出栏目、命令或依赖：编辑 registry，保持依赖在顺序上先出现。
- 更换产品：编辑项目配置及项目资料，无需改 prompt。
- 增加行业专用检索能力：在宿主或外部运行器接入，并保持只读。
- 通用核心只验证栏目、对象、证据引用和输入身份；更细的行业数值约束可在运行器中增加。
