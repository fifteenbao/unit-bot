"""PLANS 子 agent 公共运行时。

每个子 agent 提供：
  - SYSTEM_PROMPT: 本阶段调研指令
  - ALLOWED_TOOLS: 工具白名单（名称列表，从主 agent 的 ALL_TOOLS 中筛选）
  - STAGE: 阶段 key（p_research / l_lean / ...）

run_subagent() 负责：
  1. 用主 agent 的 _make_client() 构造 client（继承 OpenClaw / Anthropic 选择逻辑）
  2. 按 ALLOWED_TOOLS 过滤工具集
  3. 跑 messages loop 直到 end_turn
  4. 从最后一条 text 中抽取 ```json ...``` 代码块
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

import anthropic

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
JSON_FALLBACK_RE = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", re.DOTALL)

MAX_ITERATIONS = 30


def filter_tools(all_tools: list[dict], allowed: list[str]) -> list[dict]:
    allowed_set = set(allowed)
    return [t for t in all_tools if t.get("name") in allowed_set]


def extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出中抽取 JSON 对象。优先 ```json``` 块，失败则尝试整段最大花括号。"""
    if not text:
        return None
    m = JSON_BLOCK_RE.search(text)
    candidates = []
    if m:
        candidates.append(m.group(1))
    # 兜底：找文本里第一个看起来完整的 json 对象
    for cand in JSON_FALLBACK_RE.findall(text):
        if cand not in candidates:
            candidates.append(cand)
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def run_subagent(
    *,
    client: anthropic.Anthropic,
    system_prompt: str,
    tools: list[dict],
    dispatch: dict[str, Callable[[dict], str]],
    user_input: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    log: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """跑一个子 agent 循环，返回 (最终文本, 抽取出的 JSON 或 None)。"""

    def _log(msg: str) -> None:
        if log:
            log(msg)

    conversation: list[dict] = [{"role": "user", "content": user_input}]

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=conversation,
        )
        conversation.append({"role": "assistant", "content": response.content})

        if response.stop_reason in ("end_turn", "stop_sequence"):
            texts = [b.text for b in response.content if hasattr(b, "text") and b.type == "text"]
            full_text = "\n".join(texts)
            return full_text, extract_json(full_text)

        if response.stop_reason == "pause_turn":
            _log("→ 继续 web 检索...")
            continue

        if response.stop_reason != "tool_use":
            texts = [b.text for b in response.content if hasattr(b, "text") and b.type == "text"]
            full_text = "\n".join(texts)
            return full_text, extract_json(full_text)

        # 处理 tool_use
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            name, args = block.name, block.input
            _log(f"→ {name}({json.dumps(args, ensure_ascii=False)[:120]})")
            if name not in dispatch:
                result = json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
            else:
                try:
                    result = dispatch[name](args)
                except Exception as e:
                    result = json.dumps({"error": str(e)}, ensure_ascii=False)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })
        conversation.append({"role": "user", "content": tool_results})

    return "(子 agent 超过最大迭代次数)", None
