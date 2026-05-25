from __future__ import annotations

import json
import os
import re
import time
from typing import Any


_AIHUBMIX_BASE = os.environ.get("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1")
_AIHUBMIX_MODEL = os.environ.get("AIHUBMIX_MODEL", "gpt-5.4-mini")
_DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

_MAX_TOOL_CALLS = 6
_MAX_AGENT_ROUNDS = 8
_API_RETRY_MAX = 2
_API_RETRY_BACKOFF = (5, 15)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _api_call_with_retry(call_fn, label: str = "API"):
    import time
    last_err = None
    for attempt in range(_API_RETRY_MAX + 1):
        try:
            return call_fn()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            is_network = any(k in err_str for k in (
                "connection", "remoteprotocolerror", "timeout",
                "disconnected", "ssl", "broken pipe",
            ))
            if not is_network or attempt >= _API_RETRY_MAX:
                raise
            wait = _API_RETRY_BACKOFF[min(attempt, len(_API_RETRY_BACKOFF) - 1)]
            print(f"    ⚠ {label} 网络异常 ({type(e).__name__}), {wait}s 后重试 ({attempt+1}/{_API_RETRY_MAX})")
            time.sleep(wait)
    raise last_err


def _client_web_search(query: str, max_results: int = 8) -> str:
    import httpx as _httpx

    try:
        with _httpx.Client(timeout=15) as h:
            r = h.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; BOMAnalyzer/1.0)"},
            )
            if r.status_code != 200:
                return f"搜索失败: HTTP {r.status_code}"
            html = r.text
    except Exception as e:
        return f"搜索失败: {type(e).__name__}: {e}"

    results: list[str] = []
    links = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html
    )
    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html
    )

    for i, (url, title) in enumerate(links[:max_results]):
        title_clean = re.sub(r"<[^>]+>", "", title).strip()
        snippet_clean = ""
        if i < len(snippets):
            snippet_clean = re.sub(r"<[^>]+>", "", snippets[i]).strip()
        results.append(f"{i + 1}. {title_clean}\n   URL: {url}\n   {snippet_clean}")

    if not results:
        return f"搜索 '{query}' 无结果。"
    return "\n\n".join(results)


def _client_web_fetch(url: str, max_chars: int = 6000) -> str:
    import httpx as _httpx

    try:
        with _httpx.Client(timeout=20, follow_redirects=True) as h:
            r = h.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            if r.status_code != 200:
                return f"抓取失败: HTTP {r.status_code}"
            html = r.text
    except Exception as e:
        return f"抓取失败: {type(e).__name__}: {e}"

    html = re.sub(
        r"<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>",
        "", html, flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n…[截断, 原文共 {len(text)} 字符]"
    return f"[web_fetch: {url}]\n\n{text}"


def _run_web_agent_anthropic(system: str, user: str, max_tokens: int = 8192) -> str:
    import anthropic as _anthropic
    client = _anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user}]
    round_n = 0
    tool_call_count = 0

    server_tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209",  "name": "web_fetch"},
    ]

    while round_n < _MAX_AGENT_ROUNDS:
        round_n += 1
        budget_used = (tool_call_count >= _MAX_TOOL_CALLS and round_n >= 2) or round_n == _MAX_AGENT_ROUNDS
        if budget_used:
            messages.append({
                "role": "user",
                "content": (
                    f"⚠ 已用满 {tool_call_count}/{_MAX_TOOL_CALLS} 次工具调用预算. "
                    "立即停止搜索, 综合已收集的全部信息, 直接输出最终结果."
                ),
            })

        resp = _api_call_with_retry(
            lambda: client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=server_tools,
                messages=messages,
                **({"tool_choice": {"type": "none"}} if budget_used else {}),
            ),
            label="Anthropic",
        )
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        if tool_uses:
            tool_call_count += len(tool_uses)
        texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason == "end_turn" or texts:
            return "\n".join(texts)
        raise RuntimeError(f"意外的 stop_reason: {resp.stop_reason}")

    last_texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "\n".join(last_texts)


def _run_web_agent_openai(system: str, user: str, max_tokens: int = 8192) -> str:
    import httpx as _httpx

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    tool_call_count = 0
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "搜索互联网获取最新信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    while len(messages) < _MAX_AGENT_ROUNDS * 2:
        budget_used = (tool_call_count >= _MAX_TOOL_CALLS and len(messages) > 2)
        if budget_used:
            messages.append({
                "role": "user",
                "content": "停止搜索，直接输出最终结果。",
            })

        body: dict[str, Any] = {
            "model": _AIHUBMIX_MODEL,
            "max_completion_tokens": max_tokens,
            "messages": messages,
            "tools": openai_tools,
            "tool_choice": "none" if budget_used else "auto",
        }

        def _call():
            with _httpx.Client(timeout=120) as h:
                r = h.post(
                    f"{_AIHUBMIX_BASE}/chat/completions",
                    headers={"Authorization": f"Bearer {_env('AIHUBMIX_API_KEY')}"},
                    json=body,
                )
                if r.status_code != 200:
                    raise RuntimeError(f"AIHUBMIX 返回 {r.status_code}: {r.text[:500]}")
                return r.json()

        data = _api_call_with_retry(_call, label="AIHUBMIX")
        choice = data["choices"][0]
        message = choice["message"]
        messages.append(message)
        tcs = message.get("tool_calls") or []
        if not tcs:
            return message.get("content") or ""
        tool_call_count += len(tcs)
        messages.extend([{
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": "[web_search 已由服务端执行，结果已包含在上下文中]",
        } for tc in tcs])

    return messages[-1].get("content") or ""


def _run_web_agent_deepseek(system: str, user: str, max_tokens: int = 8192) -> str:
    import httpx as _httpx

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    round_n = 0
    tool_call_count = 0
    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "搜索互联网获取最新信息。",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "抓取指定 URL 的网页内容并提取纯文本。",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
    ]

    while round_n < _MAX_AGENT_ROUNDS:
        round_n += 1
        budget_used = (tool_call_count >= _MAX_TOOL_CALLS and round_n >= 2) or round_n == _MAX_AGENT_ROUNDS
        if budget_used:
            messages.append({
                "role": "user",
                "content": "停止搜索，直接输出最终结果。",
            })

        body: dict[str, Any] = {
            "model": _DEEPSEEK_MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
            "tool_choice": "none" if budget_used else "auto",
        }

        def _call():
            with _httpx.Client(timeout=180) as h:
                r = h.post(
                    f"{_DEEPSEEK_BASE}/chat/completions",
                    headers={"Authorization": f"Bearer {_env('DEEPSEEK_API_KEY')}"},
                    json=body,
                )
                if r.status_code != 200:
                    raise RuntimeError(f"DeepSeek 返回 {r.status_code}: {r.text[:500]}")
                return r.json()

        data = _api_call_with_retry(_call, label="DeepSeek")
        choice = data["choices"][0]
        message = choice["message"]
        messages.append(message)
        tcs = message.get("tool_calls") or []
        if not tcs:
            return message.get("content") or ""
        tool_call_count += len(tcs)

        tool_results = []
        for tc in tcs:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "?")
            fn_args_str = fn.get("arguments", "{}")
            try:
                fn_args = json.loads(fn_args_str) if fn_args_str else {}
            except Exception:
                fn_args = {}
            if fn_name == "web_search":
                result = _client_web_search(fn_args.get("query", ""))
            elif fn_name == "web_fetch":
                result = _client_web_fetch(fn_args.get("url", ""))
            else:
                result = f"未知工具: {fn_name}"
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
        messages.extend(tool_results)

    return messages[-1].get("content") or ""


def run_web_agent(system: str, user: str, max_tokens: int = 8192) -> str:
    """
    统一的 web-search 执行入口。
    优先级：
      1. AIHUBMIX_API_KEY
      2. DEEPSEEK_API_KEY
      3. ANTHROPIC_API_KEY
    """
    if _env("AIHUBMIX_API_KEY"):
        return _run_web_agent_openai(system, user, max_tokens)
    if _env("DEEPSEEK_API_KEY"):
        return _run_web_agent_deepseek(system, user, max_tokens)
    if _env("ANTHROPIC_API_KEY"):
        return _run_web_agent_anthropic(system, user, max_tokens)
    raise RuntimeError(
        "未配置 LLM API Key，无法进行 web 调研。请设置以下任一环境变量:\n"
        "  export ANTHROPIC_API_KEY=sk-ant-...\n"
        "  export AIHUBMIX_API_KEY=sk-...\n"
        "  export DEEPSEEK_API_KEY=sk-...\n"
    )
