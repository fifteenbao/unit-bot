#!/usr/bin/env python3
"""
本地测试入口 — 使用 aihubmix gpt-5.4-mini（OpenAI 兼容接口）

仅用于本地调试，不影响生产代码 agent.py。

用法：
    AIHUBMIX_API_KEY=xxx python scripts/test_local.py
    AIHUBMIX_API_KEY=xxx python scripts/test_local.py "石头P20 Ultra Plus，分析BOM成本"
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import openai
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import CLIENT_DISPATCH, CLIENT_TOOLS, SYSTEM_PROMPT, _ensure_migrated, init_standard_library
from core.components_lib import LIB_FILE
from core.db import load_db

console = Console()
MODEL = "gpt-5.4-mini"


# ── Anthropic input_schema → OpenAI function parameters ────────

def _to_openai_tools(client_tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t.get("description", ""),
                "parameters":  t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in client_tools
    ]


OPENAI_TOOLS = _to_openai_tools(CLIENT_TOOLS)


# ── Agent 循环 ───────────────────────────────────────────────────

def run_query(user_input: str, conversation: list[dict], client: openai.OpenAI) -> str:
    if not conversation:
        conversation.append({"role": "system", "content": SYSTEM_PROMPT})

    conversation.append({"role": "user", "content": user_input})

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=8192,
            messages=conversation,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
        )
        choice  = response.choices[0]
        message = choice.message
        finish  = choice.finish_reason

        conversation.append(message.model_dump(exclude_unset=False))

        if finish == "stop" or not message.tool_calls:
            return message.content or "(无回答)"

        # 处理工具调用
        tool_results = []
        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            console.print(f"  [dim]→ {name}({json.dumps(args, ensure_ascii=False)[:120]})[/dim]")

            if name not in CLIENT_DISPATCH:
                result = json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
            else:
                try:
                    result = CLIENT_DISPATCH[name](args)
                except Exception as e:
                    result = json.dumps({"error": str(e)}, ensure_ascii=False)

            tool_results.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

        conversation.extend(tool_results)


# ── CLI ──────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("AIHUBMIX_API_KEY", "")
    if not api_key:
        console.print("[red]请设置 AIHUBMIX_API_KEY 环境变量[/red]")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key, base_url="https://aihubmix.com/v1")

    _ensure_migrated()
    if not LIB_FILE.exists():
        n = init_standard_library()
        console.print(f"[dim]已初始化标准件库，共 {n} 个标准件[/dim]")

    db_count = len(load_db())
    console.print(Panel.fit(
        f"[bold cyan]BOM Agent 本地测试[/bold cyan]  [dim]模型: {MODEL}[/dim]\n"
        f"[dim]产品数据库: {db_count} 款  |  输入 exit 退出，clear 清空对话[/dim]",
        border_style="yellow",
    ))

    conversation: list[dict] = []

    # 支持命令行直接传入问题
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        console.print(f"\n[bold green]问题[/bold green]: {user_input}")
        with console.status("[dim]分析中...[/dim]", spinner="dots"):
            answer = run_query(user_input, conversation, client)
        console.print(Panel(Markdown(answer), title="[bold blue]分析结果[/bold blue]",
                            border_style="blue", padding=(1, 2)))
        return

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]你[/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            break
        if user_input.lower() == "clear":
            conversation.clear()
            console.print("[dim]对话历史已清空[/dim]")
            continue

        with console.status("[dim]分析中...[/dim]", spinner="dots"):
            answer = run_query(user_input, conversation, client)

        console.print()
        console.print(Panel(Markdown(answer), title="[bold blue]分析结果[/bold blue]",
                            border_style="blue", padding=(1, 2)))


if __name__ == "__main__":
    main()
