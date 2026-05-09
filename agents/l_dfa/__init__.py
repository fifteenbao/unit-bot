"""L · DFA 优化师 — PLANS 第 2 阶段（L 阶段 2 之 1）。

对应"价值设计流程 PLANS"图中的 L 块「DFA 优化」部分（9 项优化方向）：
最小件合并 / 紧固件减少 / 自定位防呆 / 自固定 / 防欠过约束 /
单独装配动作消除 / 焊接粘接螺纹消除 / 人体工学 / 标准化设计。

上游依赖：p_teardown + p_issues
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "l_dfa"
STAGE_TITLE = "L · DFA 优化"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
