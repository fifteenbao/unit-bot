from __future__ import annotations

import re
import time
from typing import Any

from core.llm_runtime import SERVER_WEB_TOOLS, make_runtime

_MAX_TOOL_CALLS = 6
_MAX_AGENT_ROUNDS = 8
_API_RETRY_MAX = 2
_API_RETRY_BACKOFF = (5, 15)


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


def _run_web_agent_server_tools(
    system: str,
    user: str,
    max_tokens: int = 8192,
    runtime: Any | None = None,
) -> str:
    runtime = runtime or make_runtime(require_key=True)
    client = runtime.client
    messages: list[dict] = [{"role": "user", "content": user}]
    round_n = 0
    tool_call_count = 0

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
                model=runtime.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=SERVER_WEB_TOOLS,
                messages=messages,
                **({"tool_choice": {"type": "none"}} if budget_used else {}),
            ),
            label=runtime.backend,
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


def _run_web_agent_client_tools(
    system: str,
    user: str,
    max_tokens: int = 8192,
    runtime: Any | None = None,
) -> str:
    runtime = runtime or make_runtime(require_key=True)
    client = runtime.client
    messages: list[dict] = [
        {"role": "user", "content": user},
    ]
    round_n = 0
    tool_call_count = 0
    client_tools = [
        {
            "name": "web_search",
            "description": "搜索互联网获取最新信息。",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "web_fetch",
            "description": "抓取指定 URL 的网页内容并提取纯文本。",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
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

        response = _api_call_with_retry(
            lambda: client.messages.create(
                model=runtime.model,
                max_tokens=max_tokens,
                system=system,
                tools=client_tools,
                messages=messages,
                **({"tool_choice": {"type": "none"}} if budget_used else {}),
            ),
            label=runtime.backend,
        )
        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
        if not tool_uses:
            texts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
            return "\n".join(texts)
        tool_call_count += len(tool_uses)
        tool_results = []
        for tc in tool_uses:
            fn_name = tc.name
            fn_args = tc.input or {}
            if fn_name == "web_search":
                result = _client_web_search(fn_args.get("query", ""))
            elif fn_name == "web_fetch":
                result = _client_web_fetch(fn_args.get("url", ""))
            else:
                result = f"未知工具: {fn_name}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    last = messages[-1]
    content = last.get("content", "")
    if isinstance(content, str):
        return content
    return ""


def run_web_agent(system: str, user: str, max_tokens: int = 8192) -> str:
    """
    统一 web-search 执行入口。
    只使用 core.llm_runtime 中的统一模型入口:
      1. OPENCLAW_API_KEY: Anthropic-compatible client + 客户端 web_search/web_fetch
      2. ANTHROPIC_API_KEY: Anthropic 原生 client + server-side web_search/web_fetch
    """
    runtime = make_runtime(require_key=True)
    if runtime.supports_server_web_tools:
        return _run_web_agent_server_tools(system, user, max_tokens, runtime)
    return _run_web_agent_client_tools(system, user, max_tokens, runtime)
