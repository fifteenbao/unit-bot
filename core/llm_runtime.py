from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import anthropic


DEFAULT_MODEL = "claude-sonnet-4-6"


SERVER_WEB_TOOLS: list[dict[str, Any]] = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]


@dataclass(frozen=True)
class LLMRuntime:
    client: anthropic.Anthropic
    model: str
    backend: str
    supports_server_web_tools: bool


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def configured_backend() -> str | None:
    """Return the configured runtime backend name, if any."""
    if _env("OPENCLAW_API_KEY"):
        return "openclaw"
    if _env("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def make_runtime(*, require_key: bool = False) -> LLMRuntime:
    """Build the single repo-wide LLM runtime.

    OpenClaw is treated as an Anthropic-compatible endpoint but does not support
    Anthropic server-side web tools, so callers should use client-side tools.
    """
    openclaw_key = _env("OPENCLAW_API_KEY")
    if openclaw_key:
        return LLMRuntime(
            client=anthropic.Anthropic(
                api_key=openclaw_key,
                base_url=_env("OPENCLAW_BASE_URL", "https://api.openclaw.ai/v1"),
            ),
            model=_env("OPENCLAW_MODEL", _env("UNIT_BOT_MODEL", DEFAULT_MODEL)),
            backend="openclaw",
            supports_server_web_tools=False,
        )

    if require_key and not _env("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "未配置统一 LLM 入口，无法进行 web 调研。请设置:\n"
            "  export OPENCLAW_API_KEY=...\n"
            "或\n"
            "  export ANTHROPIC_API_KEY=...\n"
        )

    return LLMRuntime(
        client=anthropic.Anthropic(),
        model=_env("ANTHROPIC_MODEL", _env("UNIT_BOT_MODEL", DEFAULT_MODEL)),
        backend="anthropic",
        supports_server_web_tools=True,
    )


def make_client_and_tools(all_tools: list[dict[str, Any]]) -> tuple[anthropic.Anthropic, list[dict[str, Any]], str]:
    """Compatibility helper for agent.py and sub-agents."""
    runtime = make_runtime()
    tools = all_tools
    if not runtime.supports_server_web_tools:
        tools = [t for t in all_tools if t.get("type") not in {
            "web_search_20260209",
            "web_fetch_20260209",
        }]
    return runtime.client, tools, runtime.model
