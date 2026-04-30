#!/usr/bin/env python3
"""
拆机 BOM 生成器 — Stage 0 + 4-Stage Pipeline

职责：爬取元器件型号 + 判断置信度 + 对照 8 桶框架审计覆盖与成本偏差
价格来源：components_lib.csv（人工维护，权威来源）→ standard_parts.json（基准 fallback）
            不调用 API 查价；定价更新请维护 data/lib/components_lib.csv

8 桶标准模板：core/bom_8bucket_framework.json（通用、无敏感数据）
  - 桶定义、典型子项、行业占比基准、归桶边界、user_value_weight、dfma_levers 全部来自该文件
  - 修改模板后本脚本自动生效，无需改代码

职责边界：
  - 本脚本只产出"是什么成本"——8 桶占比、BOM/MSRP、偏差告警
  - 降本建议（DFMA 抓手 / 价值-成本矩阵）由 agent.py 的 /dfma 命令产出

用法：
    python scripts/gen_teardown.py "石头G30S Pro"
    python scripts/gen_teardown.py "科沃斯X8 Pro" --msrp 6999
    python scripts/gen_teardown.py --csv data/teardowns/xxx.csv "机型名"

输出：data/teardowns/{model_slug}_{YYYYMMDD}_teardown.csv
      (含 _unit_price / _line_cost / _price_src, 日期后缀便于版本追溯)

Pipeline：
  Stage 0 FCC 上游             读 data/teardowns/fcc/{slug}/*_fcc_*.csv（fetch_fcc.py find+ocr 产出）
                               有则注入 Stage 1 prompt 作为已知项 + Stage 1 后优先合并去重；无则静默跳过
  Stage 1 Discovery            多源调研（FCCID.io / 蓝牙SIG / MyFixGuide / 知乎 / 评测站）,
                               prompt 注入 framework 桶清单 + Stage 0 FCC 已识别零件
  Stage 2 Heuristic Enrichment SoC 识别 → 推导 PMIC/RAM/ROM 伴随件
  Stage 3 Coverage Audit       对照 framework typical_items 报缺失关键子项
  Stage 4 Aggregate & Bias     8 桶金额汇总 + ±5% 占比偏差告警 + BOM/MSRP 比

FCC 上游采集（独立脚本，按需先跑）：
    python scripts/fetch_fcc.py find <型号>   # 查 PDF 链接，不下载
    python scripts/fetch_fcc.py ocr  <型号>   # 下载 PDF + 视觉 OCR 识别芯片丝印
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Optional

import anthropic

ROOT         = Path(__file__).parent.parent
DATA_DIR      = ROOT / "data"
TEARDOWN_DIR  = DATA_DIR / "teardowns"
PARTS_FILE    = DATA_DIR / "lib" / "standard_parts.json"
COMP_LIB_FILE = DATA_DIR / "lib" / "components_lib.csv"

sys.path.insert(0, str(ROOT))
from core.bucket_framework import (  # noqa: E402
    audit_coverage,
    bucket_keys,
    bucket_pct_avg,
    bucket_pct_range,
    bucket_pct_tolerance,
    buckets_ordered,
    expected_bom_msrp_ratio,
    render_prompt_bucket_section,
    typical_items_with_qty,
)
from core.bom_rules import (  # noqa: E402
    BUCKET_DEFAULT_PRICE,
    aux_price,
    classify,
    is_aggregate,
    is_aux,
)
from core.components_lib import load_lib  # noqa: E402

# ── BOM 8桶 (从 data/lib/bom_8bucket_framework.json 动态加载) ───────
BUCKETS = buckets_ordered()                      # [(key, name_cn), ...]
BUCKET_MAP = {k: v for k, v in BUCKETS}
BUCKET_THEORY = {k: bucket_pct_range(k) for k, _ in BUCKETS}

CSV_FIELDS = [
    "bom_bucket", "section", "name", "model", "type",
    "spec", "manufacturer", "qty", "source_url", "updated_at", "product_source",
    "confidence",
    # Stage 4 查价补充字段 (有则写, 没有则空)
    "_unit_price", "_line_cost", "_price_src",
]



# ══════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════

def _slug(model: str) -> str:
    return re.sub(r"[\s\-]+", "", model)


def _norm_price(val) -> float:
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0


def _norm_qty(val) -> int:
    try:
        return max(1, int(val or 1))
    except (ValueError, TypeError):
        return 1


def _load_standard_parts() -> dict:
    if PARTS_FILE.exists():
        return json.loads(PARTS_FILE.read_text(encoding="utf-8"))
    return {}


# ══════════════════════════════════════════════════════════════════
#  CSV 读写
# ══════════════════════════════════════════════════════════════════

def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(rows: list[dict], path: Path, model: str) -> None:
    if not rows:
        # 不写出只有表头的空文件 (避免下次 --csv 加载被骗进 0 行审计)
        print(f"  ⚠ 零件列表为空, 跳过写出 (避免产生只含表头的文件)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    for r in rows:
        r.setdefault("product_source", model)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def find_csv(model: str) -> Optional[Path]:
    """查找某机型已有的拆机 CSV, 优先返回最新一份 (按 mtime)。

    匹配顺序:
      1. 精确无日期版: {slug}_teardown.csv (兼容老文件)
      2. 带日期版: {slug}_{YYYYMMDD}_teardown.csv 中 mtime 最新
      3. 模糊包含 slug 子串的任意 _teardown*.csv 中 mtime 最新
    """
    slug = _slug(model)
    exact = TEARDOWN_DIR / f"{slug}_teardown.csv"
    if exact.exists():
        return exact
    candidates = [
        p for p in TEARDOWN_DIR.glob("*_teardown*.csv")
        if slug.lower() in p.name.lower() or p.stem.lower().startswith(slug.lower()[:6])
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ══════════════════════════════════════════════════════════════════
#  Stage 0 — FCC 上游加载（fetch_fcc.py find+ocr 产出）
#
#  读取 data/teardowns/fcc/{slug}/*_fcc_*.csv：
#    - 有则注入 Stage 1 prompt 作为"已识别零件"
#    - Stage 1 完成后再用 (bucket, name) key 优先合并去重
#    - 无则静默跳过，不影响主流程
#  采集脚本独立：python scripts/fetch_fcc.py find/ocr <型号>
# ══════════════════════════════════════════════════════════════════

FCC_DIR = DATA_DIR / "teardowns" / "fcc"


def _norm_name(s: str) -> str:
    """归一化零件名用于 dedup，去空格/标点/大小写。"""
    return re.sub(r"[\s/+\-·,，。、()（）]+", "", (s or "")).lower()


def load_fcc_rows(slug: str) -> list[dict]:
    """扫描 data/teardowns/fcc/{slug}/*_fcc_*.csv，返回最新文件的行列表。"""
    fcc_slug_dir = FCC_DIR / slug
    if not fcc_slug_dir.exists():
        return []
    candidates = sorted(fcc_slug_dir.glob(f"{slug}_fcc_*.csv"))
    if not candidates:
        return []
    newest = candidates[-1]
    rows = load_csv(newest)
    print(f"  [Stage 0] FCC 上游：{newest.name}（{len(rows)} 条）")
    return rows


def _merge_fcc_first(fcc_rows: list[dict], discovery_rows: list[dict]) -> list[dict]:
    """FCC 行优先合并：同 (bom_bucket, norm_name) key 时保留 FCC 行，丢弃 discovery 行。"""
    fcc_keys: set[tuple] = {
        (r.get("bom_bucket", ""), _norm_name(r.get("name", "")))
        for r in fcc_rows
    }
    deduped_discovery = [
        r for r in discovery_rows
        if (r.get("bom_bucket", ""), _norm_name(r.get("name", ""))) not in fcc_keys
    ]
    merged = list(fcc_rows) + deduped_discovery
    dropped = len(discovery_rows) - len(deduped_discovery)
    if dropped:
        print(f"  ✓ FCC 优先合并：保留 {len(fcc_rows)} 条 FCC 行，去重 {dropped} 条 web 行")
    return merged


# ══════════════════════════════════════════════════════════════════
#  通用 web_agent — 自动切换 Anthropic / OpenAI-compatible backend
#
#  优先级：
#    1. AIHUBMIX_API_KEY 存在 → OpenAI-compatible（aihubmix / 任意兼容接口）
#    2. ANTHROPIC_API_KEY 存在 → Anthropic 原生
#  AIHUBMIX_MODEL / AIHUBMIX_BASE_URL 可覆盖默认值。
# ══════════════════════════════════════════════════════════════════

import os as _os

_AIHUBMIX_KEY  = _os.environ.get("AIHUBMIX_API_KEY", "")
_AIHUBMIX_BASE = _os.environ.get("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1")
_AIHUBMIX_MODEL = _os.environ.get("AIHUBMIX_MODEL", "gpt-5.4-mini")

# LLM web agent 上限控制 (避免 LLM 无限搜索浪费 token + 防止 messages 体积过大触发代理 TCP 断).
# 用"工具调用总次数"而非"轮数" — 单轮可能并发 2-3 个 tool call, 按轮数会失控.
# 撞上限不抛错: 注入"停止搜索"指令 + tool_choice="none" 让模型输出最终 JSON.
_MAX_TOOL_CALLS = 6      # 工具调用总次数上限 (累计, 含 web_fetch + web_search)
_MAX_AGENT_ROUNDS = 8    # 兜底硬上限 — 即使 LLM 不调工具但反复让脚本走流程也不超过这个

# API 请求重试 (代理不稳/服务端断连时自动重试)
_API_RETRY_MAX     = 2          # 最多重试 2 次 (共 3 次尝试)
_API_RETRY_BACKOFF = (5, 15)    # 指数退避 (秒): 第 1 次重试等 5s, 第 2 次等 15s


def _api_call_with_retry(call_fn, label: str = "API"):
    """对 LLM API 调用做重试封装. 处理代理断连 / 临时网络抖动.

    call_fn: 无参 callable, 调用一次 LLM API 返回 response 对象
    label:   日志前缀 (如 "Anthropic" / "OpenAI")
    """
    import time
    last_err = None
    for attempt in range(_API_RETRY_MAX + 1):  # 0, 1, 2 = 共 3 次
        try:
            return call_fn()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            # 只重试网络/连接类错误, 其他直接抛 (如 401/429/500)
            is_network = any(k in err_str for k in (
                "connection", "remoteprotocolerror", "timeout",
                "disconnected", "ssl", "broken pipe",
            ))
            if not is_network or attempt >= _API_RETRY_MAX:
                raise
            wait = _API_RETRY_BACKOFF[min(attempt, len(_API_RETRY_BACKOFF) - 1)]
            print(f"    ⚠ {label} 网络异常 ({type(e).__name__}), {wait}s 后重试 ({attempt+1}/{_API_RETRY_MAX})")
            time.sleep(wait)
    raise last_err  # 兜底, 实际走不到

# Anthropic server-side tools（原生 backend 用）
_ANTHROPIC_SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209",  "name": "web_fetch"},
]

# OpenAI-compatible web_search tool（aihubmix 支持）
_OPENAI_SERVER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取最新信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    }
]


def _run_web_agent_anthropic(system: str, user: str, max_tokens: int = 8192) -> str:
    import time
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user}]
    round_n = 0
    tool_call_count = 0  # 累计工具调用次数 (替代轮数, 单轮可能并发多个 tool_call)

    while round_n < _MAX_AGENT_ROUNDS:
        round_n += 1
        # 触底: 累计 tool call 数 ≥ 上限, 或撞 round 兜底 → 强制 finalize
        budget_used = tool_call_count >= _MAX_TOOL_CALLS or round_n == _MAX_AGENT_ROUNDS
        if budget_used:
            messages.append({
                "role": "user",
                "content": (
                    f"⚠ 已用满 {tool_call_count}/{_MAX_TOOL_CALLS} 次工具调用预算. "
                    "立即停止搜索, 综合已收集的全部信息, 直接输出最终 JSON 数组. "
                    "不要再调用任何工具."
                ),
            })

        print(f"    → 等待 LLM 响应 (round {round_n}, 已用 {tool_call_count}/{_MAX_TOOL_CALLS} 次工具)…")
        t0 = time.monotonic()
        resp = _api_call_with_retry(
            lambda: client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=_ANTHROPIC_SERVER_TOOLS,
                messages=messages,
                **({"tool_choice": {"type": "none"}} if budget_used else {}),
            ),
            label="Anthropic",
        )
        elapsed = time.monotonic() - t0
        messages.append({"role": "assistant", "content": resp.content})

        # 打印本轮工具调用
        tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        if tool_uses:
            tool_call_count += len(tool_uses)
            for tu in tool_uses:
                tool_name = getattr(tu, "name", "?")
                tool_input = getattr(tu, "input", {}) or {}
                hint = tool_input.get("query") or tool_input.get("url") or ""
                hint = (hint[:80] + "…") if len(hint) > 80 else hint
                print(f"    ⏱ [round {round_n}, tools {tool_call_count}/{_MAX_TOOL_CALLS}] {tool_name}: {hint}  ({elapsed:.1f}s)")
        else:
            print(f"    ⏱ [round {round_n}] (直接返回, tools {tool_call_count}/{_MAX_TOOL_CALLS})  ({elapsed:.1f}s)")

        if resp.stop_reason in ("end_turn", "pause_turn"):
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            return "\n".join(texts)

        texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        if texts:
            return "\n".join(texts)
        raise RuntimeError(f"意外的 stop_reason: {resp.stop_reason}")

    # 撞 _MAX_AGENT_ROUNDS 兜底: 抓最后一条 assistant 文本块
    last_texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "\n".join(last_texts)


def _run_web_agent_openai(system: str, user: str, max_tokens: int = 8192) -> str:
    import openai as _openai
    import httpx as _httpx
    import time

    client = _openai.OpenAI(api_key=_AIHUBMIX_KEY, base_url=_AIHUBMIX_BASE)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    round_n = 0

    tool_call_count = 0  # 累计工具调用次数 (替代轮数, 单轮可能并发多个 tool_call)
    while round_n < _MAX_AGENT_ROUNDS:
        round_n += 1
        # 触底: 累计 tool call 数 ≥ 上限, 或撞 round 兜底 → 强制 finalize
        budget_used = tool_call_count >= _MAX_TOOL_CALLS or round_n == _MAX_AGENT_ROUNDS
        if budget_used:
            messages.append({
                "role": "user",
                "content": (
                    f"⚠ 已用满 {tool_call_count}/{_MAX_TOOL_CALLS} 次工具调用预算. "
                    "立即停止搜索, 综合已收集的全部信息, 直接输出最终 JSON 数组. "
                    "不要再调用任何工具."
                ),
            })

        print(f"    → 等待 LLM 响应 (round {round_n}, 已用 {tool_call_count}/{_MAX_TOOL_CALLS} 次工具)…")
        t0 = time.monotonic()
        resp = _api_call_with_retry(
            lambda: client.chat.completions.create(
                model=_AIHUBMIX_MODEL,
                max_completion_tokens=max_tokens,
                messages=messages,
                tools=_OPENAI_SERVER_TOOLS,
                tool_choice="none" if budget_used else "auto",
            ),
            label="AIHUBMIX",
        )
        elapsed = time.monotonic() - t0
        choice  = resp.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_unset=False))

        # 打印本轮工具调用
        tcs = message.tool_calls or []
        if tcs:
            tool_call_count += len(tcs)
            for tc in tcs:
                fn_name = tc.function.name if tc.function else "?"
                args_raw = tc.function.arguments if tc.function else ""
                hint = ""
                try:
                    args = json.loads(args_raw) if args_raw else {}
                    hint = args.get("query") or args.get("url") or ""
                except Exception:
                    hint = args_raw[:60]
                hint = (hint[:80] + "…") if len(hint) > 80 else hint
                print(f"    ⏱ [round {round_n}, tools {tool_call_count}/{_MAX_TOOL_CALLS}] {fn_name}: {hint}  ({elapsed:.1f}s)")
        else:
            print(f"    ⏱ [round {round_n}] (直接返回, tools {tool_call_count}/{_MAX_TOOL_CALLS})  ({elapsed:.1f}s)")

        if choice.finish_reason == "stop" or not tcs:
            return message.content or ""

        # 处理 web_search 工具调用（aihubmix 会直接返回结果，无需本地执行）
        tool_results = []
        for tc in tcs:
            tool_results.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      f"[web_search 已由服务端执行，结果已包含在上下文中]",
            })
        messages.extend(tool_results)

    # 撞 _MAX_AGENT_ROUNDS 兜底: 抓最后一条 assistant 消息内容
    return message.content or ""


def _run_web_agent(system: str, user: str, max_tokens: int = 8192) -> str:
    if _AIHUBMIX_KEY:
        return _run_web_agent_openai(system, user, max_tokens)
    return _run_web_agent_anthropic(system, user, max_tokens)


def _extract_json_array(text: str) -> list[dict]:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"响应中未找到 JSON 数组（前500字）：\n{text[:500]}")
    return json.loads(text[start:end])


# ══════════════════════════════════════════════════════════════════
#  Stage 1 — Discovery（多源调研，生成原始零件列表）
# ══════════════════════════════════════════════════════════════════

_DISCOVERY_SYSTEM = (
    "你是一名资深的智能硬件逆向工程与供应链审计专家，专注于扫地机器人（RVC）垂直领域。"
    "你擅长通过交叉验证法（Triangulation）从非结构化情报中还原底层 BOM 架构。"

    "【情报源优先级】：\n"
    "1. 准入合规维度：FCCID.io（内部照片/框图）、Bluetooth SIG（SoC/通讯模组主轴）；\n"
    "2. 深度逆向维度：MyFixGuide、我爱音频网（52audio）等元器件级拆解报告；\n"
    "3. 供应链情报维度：知乎『Robot森』等垂直大V的 CMF 与结构件分析、芯片原厂"
    "（Rockchip/Allwinner/TI/ST/InvenSense）参考设计方案；\n"
    "4. 市场实测维度：VacuumWars、RTINGS 等性能规格对标数据。\n"

    "【集成指令】：\n"
    "1. 针对缺失物料，需基于主控方案进行启发式补全（Heuristic Enrichment），并标记 confidence='inferred'；\n"
    "2. 严格遵守『8 桶成本框架』进行分类，确保各桶占比符合旗舰机基准分布。\n"

    "【输出规范】：严格按指定 JSON 格式输出，禁止任何解释性文字或 Markdown 标记。"
)

_DISCOVERY_PROMPT = """\
请为 **{model}**（建议零售价约 {msrp} 元）从多个数据源生成完整拆机 BOM 清单。

**重要约束 — 严禁脑补海外型号别名**:
- 只搜索上方"已知规格"段中明确给出的 model 名 (中文/英文都可) 和"信息源链接"
- **不要**自行联想"该机型海外可能叫 Freo X / RoboMoo Y / X-Plus" 等. 即使你以为有这种映射也禁止假设
- 国内/海外型号别名只在 model_aliases.csv 中维护, 不在任何 prompt 中存在
- 如果上方未提供英文名, 仅用 model 中文原名搜索. 找不到资料也比错误关联好

**操作步骤（按顺序执行）— 节省 token 的关键: 优先抓取已提供链接, 不要重复搜索已知规格**

0. **优先抓取信息源链接** (如果上方"优先操作"段有给出)
   - 对每个 URL: web_fetch 抓取 → 提取拆机内容
   - 这一步通常足以覆盖 80%+ 信息, 完成后只需做必要补充搜索

1. **补充搜索: 拆机报告** (上述链接信息不足时)
   - web_search: "{model} site:myfixguide.com"
   - web_search: "{model} 拆机报告 PCB 芯片 知乎"
   - web_search: "{model} teardown internals disassembly"

2. **补充搜索: 蓝牙SIG认证**（可确认芯片型号）
   - web_search: "{model} bluetooth qualified chip"

3. **补充搜索: 规格/评测**（已知规格不要重复查）
   - web_search: "{model} SoC CPU 雷达型号"

4. **综合以上来源**，输出下方 JSON

---

**8个BOM桶说明**（来自 core/bom_8bucket_framework.json，通用标准模板）

{bucket_section}

---

**输出格式**（直接输出 JSON 数组，不要 markdown 代码块）：
[
  {{
    "bom_bucket": "compute_electronics",
    "section": "主板",
    "name": "SoC",
    "model": "RK3588S",
    "type": "主控芯片",
    "spec": "八核A76+A55，6T NPU",
    "manufacturer": "瑞芯微",
    "qty": 1,
    "source_url": "https://..."
  }}
]

source_url 说明：填写该零件名称/型号信息的具体来源页面 URL（拆机报告页、评测文章、蓝牙SIG认证页等）；若为行业推断则留空。

---

**硬约束（必须满足，否则视为失败）**：

1. **每桶 ≥ 3 件**（能源桶除外，≥ 1 件即可）。拆机报告未提及的也要按 typical_items 推断补齐，标注 `confidence: inferred`。

2. **基站系统** `dock_station` 必须覆盖以下 4 大件（如果该机型带基站）：
   - 基站外壳（五大件，归一行）
   - 基站电源板
   - 基站集尘风机（若带集尘功能）
   - 基站清水桶 / 污水桶（若带自动换水）

3. **算力桶** `compute_electronics` 必须至少包含：
   - 主控 SoC（哪怕只知道厂商、型号填 "未确认" 也要列出）
   - 主板 PCB
   - 无线模组（Wi-Fi/BT）

4. **清洁桶** `cleaning` 若该机型带拖地，必须包含：
   - 拖布本体（区分双面/普通）
   - 清水泵
   - 主机水箱（清水/污水）

5. **bom_bucket 字段**必须严格使用 8 个合法 key（见上方桶说明），不要自创命名。

6. **name 字段**优先使用 framework `typical_items` 的**完整名称**（如 "主控 SoC"、"基站集尘风机"、"双面拖布"），便于下游匹配标准件库。

**目标**：覆盖全部 8 个桶，总行数 ≥ 25（入门机）/ 35（中端）/ 45（旗舰带基站）。\
"""



def _render_product_context(model: str) -> str:
    """从 products_db.json 取已知规格 + 用户提供的信息源链接, 注入 Stage 1 prompt 顶部.

    返回 markdown 段落; 找不到机型 → 返回空串.
    目的: 减少 LLM 重复查询已有数据 + 强制优先 web_fetch 用户提供的权威源.
    """
    db = _load_products_db()
    slug = _slug(model).lower()
    entry = None
    for key, val in db.items():
        if _slug(key).lower() == slug or slug in _slug(key).lower():
            entry = val
            break
    if not entry:
        return ""

    lines = ["", "【优先操作 — 用户已提供权威信息源 + 已知规格, 务必先用 web_fetch 抓取链接, 不要重复搜索】", ""]

    # 1. 用户提供的信息源链接 (web_research)
    urls = (entry.get("data_sources") or {}).get("web_research", []) or []
    if urls:
        lines.append("**信息源链接 (优先 web_fetch)**:")
        for u in urls:
            lines.append(f"  - {u}")
        lines.append("")

    # 2. 已知规格 (specs)
    specs = entry.get("specs") or {}
    if specs:
        spec_map = {
            "suction_power_pa":     "吸力",
            "battery_capacity_mah": "电池",
            "battery_life_min":     "续航",
            "obstacle_height_cm":   "越障高度",
            "navigation":           "导航方式",
        }
        lines.append("**已知规格** (来自 products_db, 不要重复搜索):")
        for k, label in spec_map.items():
            v = specs.get(k)
            if v:
                lines.append(f"  - {label}: {v}")

    # 3. 卖点摘要 (notes)
    notes = (entry.get("notes") or "").strip()
    if notes:
        lines.append(f"  - 卖点摘要: {notes}")

    lines.extend(["", "---", ""])
    return "\n".join(lines)


def stage1_discovery(model: str, msrp: float,
                     fcc_rows: list[dict] | None = None) -> list[dict]:
    import time
    src = "FCC + 多源调研" if fcc_rows else "多源调研"
    print(f"  [Stage 1] {src} {model}…")

    # 注入 products_db 已知规格 + 用户提供的信息源链接 (减少 token 浪费)
    product_ctx = _render_product_context(model)
    if product_ctx:
        url_count = product_ctx.count("\n  - http")
        spec_count = product_ctx.count("\n  - ") - url_count
        print(f"  → 已注入 products_db 上下文 ({url_count} 个信息源, {spec_count} 项规格)")
    else:
        print(f"  ⚠ products_db 中未找到 {model!r}, 仅靠 web_search (建议先维护 products.csv)")

    # FCC 缺失时提示
    if not fcc_rows:
        print(f"  ⚠ 未找到 FCC 数据, 跑 'python scripts/fetch_fcc.py find {model!r}' 可补充上游信息")

    fcc_hint = ""
    if fcc_rows:
        lines = [f"  - [{r.get('bom_bucket','')}] {r.get('name','')} {r.get('model','')}".rstrip()
                 for r in fcc_rows]
        fcc_hint = (
            "\n\n【FCC 已识别零件 — 只需补缺口，勿重复以下条目】\n"
            + "\n".join(lines)
            + "\n"
        )
    prompt = product_ctx + _DISCOVERY_PROMPT.format(
        model=model,
        msrp=int(msrp),
        bucket_section=render_prompt_bucket_section(),
    ) + fcc_hint

    t0 = time.monotonic()
    try:
        text = _run_web_agent(_DISCOVERY_SYSTEM, prompt, max_tokens=8192)
    except Exception as e:
        # API 网络错误 (代理断连等) 给出明确出口提示, 不再爆栈
        elapsed = time.monotonic() - t0
        err_str = str(e).lower()
        is_network = any(k in err_str for k in (
            "connection", "remoteprotocolerror", "timeout",
            "disconnected", "ssl", "broken pipe",
        ))
        if is_network:
            raise RuntimeError(
                f"Stage 1 LLM 网络异常 (已重试 {_API_RETRY_MAX} 次仍失败, 总耗时 {elapsed:.0f}s):\n"
                f"  {type(e).__name__}: {e}\n\n"
                f"原因可能是:\n"
                f"  • HTTPS_PROXY 代理在长 LLM 响应上 TCP 断开 (常见)\n"
                f"  • AIHUBMIX 服务端临时不稳\n\n"
                f"建议:\n"
                f"  1. 关代理直连: unset HTTPS_PROXY HTTP_PROXY 后重试\n"
                f"  2. 换 backend: unset AIHUBMIX_API_KEY 走 ANTHROPIC 原生\n"
                f"  3. 复用历史 CSV: --csv data/teardowns/<slug>_<date>_teardown.csv 跳过 Stage 1\n"
            ) from e
        raise
    elapsed = time.monotonic() - t0
    print(f"  ⏱ Stage 1 LLM 调用完成 ({elapsed:.1f}s)")
    try:
        rows = _extract_json_array(text)
    except ValueError as e:
        raise RuntimeError(
            f"Stage 1 LLM 未返回合法 JSON 数组 (可能未找到机型资料)。\n"
            f"建议: 换更通用的机型名 (如 '石头G30S Pro' → 'Roborock G30S Pro') 或手工提供拆机 CSV 后用 --csv 加载。\n"
            f"{e}"
        ) from e
    if not rows:
        # 保留 LLM raw 供排查
        raw_path = TEARDOWN_DIR / f"{_slug(model)}_stage1_raw.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(text, encoding="utf-8")
        raise RuntimeError(
            f"Stage 1 LLM 返回空数组 [] — 未找到 {model!r} 的拆机情报。\n"
            f"原始响应已存至: {raw_path}\n"
            f"常见原因:\n"
            f"  1. 机型名太小众/冷门, 公开渠道无拆机资料\n"
            f"  2. 品牌名拼写不匹配 (试试英文名 / 官方全名)\n"
            f"  3. LLM 认为证据不足, 拒绝虚构 (可接受)\n"
            f"解决:\n"
            f"  • 换更准确的机型名, 如 '美的 W20 Pro' → 'Midea W20 Pro' / 'Midea M9 Pro'\n"
            f"  • 若已有拆机报告, 手工填 CSV 后用 --csv 跳过 Stage 1"
        )

    today = __import__("datetime").date.today().isoformat()
    for r in rows:
        r["product_source"] = model
        for key in CSV_FIELDS:
            r.setdefault(key, "")
        r["qty"]        = _norm_qty(r.get("qty"))
        r["updated_at"] = today

    print(f"  ✓ Stage 1 完成：{len(rows)} 条零件记录")
    return rows


# ══════════════════════════════════════════════════════════════════
#  Stage 2 — Heuristic Enrichment（SoC 推导伴随件）
# ══════════════════════════════════════════════════════════════════

def stage2_heuristic_enrichment(rows: list[dict]) -> list[dict]:
    """
    根据 standard_parts.json heuristics，若识别到 SoC 型号，
    自动补充 PMIC / RAM / ROM 等伴随件（避免遗漏但不重复添加）。
    """
    parts = _load_standard_parts()
    heuristics: dict = parts.get("heuristics", {})
    if not heuristics:
        return rows

    # 找已有 SoC 型号
    existing_models = {(r.get("bom_bucket", ""), r.get("model", "").upper()) for r in rows}
    existing_names  = {r.get("name", "").lower() for r in rows}

    added = 0
    for row in list(rows):
        if row.get("bom_bucket") != "compute_electronics":
            continue
        soc_model = (row.get("model") or "").strip().upper()
        if soc_model not in heuristics:
            # 模糊匹配：RK3566 匹配 "rk3566"
            for hkey in heuristics:
                if hkey.upper() in soc_model or soc_model.startswith(hkey.upper()[:4]):
                    soc_model = hkey.upper()
                    break
            else:
                continue

        rules = heuristics[soc_model.upper()] if soc_model.upper() in heuristics else heuristics.get(soc_model, {})
        if not rules:
            continue

        today = __import__("datetime").date.today().isoformat()
        src = row.get("product_source", "")

        # PMIC
        pmic = rules.get("pmic")
        if pmic and ("compute_electronics", pmic.upper()) not in existing_models and "pmic" not in existing_names:
            rows.append({
                "bom_bucket": "compute_electronics", "section": "主板",
                "name": "PMIC", "model": pmic, "type": "电源管理",
                "spec": f"配套 {soc_model} 多路 DC-DC+LDO",
                "manufacturer": "瑞芯微" if pmic.startswith("RK") else "",
                "qty": 1, "source_url": "", "updated_at": today,
                "product_source": src,
            })
            existing_models.add(("compute_electronics", pmic.upper()))
            existing_names.add("pmic")
            added += 1

        # RAM
        ram = rules.get("ram")
        if ram and "ram" not in existing_names and "lpddr" not in " ".join(existing_names):
            rows.append({
                "bom_bucket": "compute_electronics", "section": "主板",
                "name": "RAM", "model": "", "type": "内存",
                "spec": ram, "manufacturer": "三星/海力士/美光",
                "qty": 1, "source_url": "", "updated_at": today,
                "product_source": src,
            })
            existing_names.add("ram")
            added += 1

        # ROM
        rom = rules.get("rom")
        if rom and "rom" not in existing_names and "emmc" not in " ".join(existing_names):
            rows.append({
                "bom_bucket": "compute_electronics", "section": "主板",
                "name": "ROM", "model": "", "type": "闪存",
                "spec": rom, "manufacturer": "三星/Kingston",
                "qty": 1, "source_url": "", "updated_at": today,
                "product_source": src,
            })
            existing_names.add("rom")
            added += 1

        # AI 授权（RK3588S 等高端 SoC）
        if rules.get("ai_license") and "ai授权" not in existing_names and "算法版税" not in existing_names:
            rows.append({
                "bom_bucket": "mva_software", "section": "软件授权",
                "name": "AI算法授权", "model": "", "type": "软件",
                "spec": f"NPU 算法版税（{soc_model}平台）",
                "manufacturer": "", "qty": 1, "source_url": "", "updated_at": today,
                "product_source": src,
            })
            existing_names.add("ai授权")
            added += 1

    if added:
        print(f"  [Stage 2] Heuristic 推导补充 {added} 条伴随件")
    else:
        print(f"  [Stage 2] Heuristic 推导：无需补充")
    return rows


# ══════════════════════════════════════════════════════════════════
#  桶名归一化 (LLM 偶尔自创命名, 做一次兜底映射)
# ══════════════════════════════════════════════════════════════════

_BUCKET_ALIASES = {
    # 常见错写 → 正确 key
    "perception_system":   "perception",
    "perception_sensor":   "perception",
    "sensing":             "perception",
    "actuation_drive":     "power_motion",
    "actuation":           "power_motion",
    "drive_power":         "power_motion",
    "motion":              "power_motion",
    "cleaning_function":   "cleaning",
    "cleaning_module":     "cleaning",
    "energy_system":       "energy",
    "battery":             "energy",
    "power_supply":        "energy",
    "cmf_structural":      "structure_cmf",
    "structural":          "structure_cmf",
    "structure":           "structure_cmf",
    "cmf":                 "structure_cmf",
    "chassis":             "structure_cmf",
    "dock":                "dock_station",
    "station":             "dock_station",
    "compute":             "compute_electronics",
    "electronics":         "compute_electronics",
    "software":            "mva_software",
    "mva":                 "mva_software",
}


def normalize_buckets(rows: list[dict]) -> list[dict]:
    """把 LLM 可能自创的桶名归一化到 framework 的 8 个合法 key。"""
    valid = set(bucket_keys())
    fixes = 0
    unknown: dict[str, int] = {}
    for r in rows:
        b = (r.get("bom_bucket") or "").strip()
        if b in valid:
            continue
        mapped = _BUCKET_ALIASES.get(b.lower())
        if mapped:
            r["bom_bucket"] = mapped
            fixes += 1
        else:
            unknown[b] = unknown.get(b, 0) + 1

    if fixes:
        print(f"  [Normalize] 桶名归一化: 修复 {fixes} 条 LLM 自创命名")
    if unknown:
        print(f"  ⚠ {sum(unknown.values())} 条 bucket 未识别: " +
              ", ".join(f"{k}(×{v})" for k, v in unknown.items()))
    return rows


def apply_rules_overlay(rows: list[dict]) -> list[dict]:
    """用 KEYWORD_RULES 对 LLM 产出做二次归桶 + 打聚合标记 + 记 lib hint。

    目的: 复用 analyze_c33 打磨过的 70+ 规则, 让竞品 BOM 享受同级分类精度。
    优先级: 规则命中 > LLM 给的桶 (规则准确度高, LLM 常归错)。

    产生的新字段:
      _rule_bucket: 规则认定的桶 (可能覆盖 LLM 的 bom_bucket)
      _lib_hint:    用于 Stage 4 查 components_lib 的关键词
      _agg_note:    聚合标记 (带 "(聚合)" 的件整机计一次)
      _is_aux:      是否为辅料件 (按 aux_price 分档定价)
    """
    overrides = 0
    aggregates = 0
    aux_count = 0
    for r in rows:
        name = r.get("name", "")
        spec = r.get("spec", "")
        llm_bucket = (r.get("bom_bucket") or "").strip()
        # 区域推断 (仅从 name 启发, LLM 不给父子链)
        region = "robot"
        if "基站" in name or "dock" in name.lower() or llm_bucket == "dock_station":
            region = "dock"
        if any(k in name for k in ("包装", "外箱", "彩箱", "说明书")):
            region = "package"

        rule_bucket, hint, note = classify(name, spec, region)
        if rule_bucket and rule_bucket != llm_bucket:
            r["bom_bucket"] = rule_bucket
            overrides += 1
        r["_rule_bucket"] = rule_bucket or llm_bucket
        r["_lib_hint"] = hint
        r["_agg_note"] = note
        if is_aggregate(note):
            aggregates += 1
        if is_aux(name):
            r["_is_aux"] = True
            aux_count += 1
        else:
            r["_is_aux"] = False

    if overrides:
        print(f"  [Rules] 规则覆盖 LLM 归桶: {overrides} 条 (KEYWORD_RULES 比 LLM 更精确)")
    if aggregates:
        print(f"  [Rules] 识别聚合件: {aggregates} 条 (整机计一次, 不按 qty 累加)")
    if aux_count:
        print(f"  [Rules] 识别辅料件: {aux_count} 条 (按分档价兜底, 避免误匹高价 lib)")
    return rows


# ══════════════════════════════════════════════════════════════════
#  Stage 3 — Coverage Audit（对照 framework typical_items 检查覆盖）
# ══════════════════════════════════════════════════════════════════

def stage3_coverage_audit(rows: list[dict]) -> dict:
    """对照 framework typical_items 报告每桶缺失关键子项。"""
    coverage = audit_coverage(rows)
    total = len(rows)

    print(f"\n  [Stage 3] 8桶覆盖审计（共 {total} 条 | 对照 core/bom_8bucket_framework.json）")
    print(f"  {'桶':16s} {'行数':>4s}  {'状态':<24s}  缺失关键子项")
    print(f"  {'-'*90}")

    alerts: list[str] = []
    bucket_report: dict[str, dict] = {}
    for bkt, name_cn in BUCKETS:
        info = coverage[bkt]
        missing_preview = ", ".join(info["missing"][:3])
        if info["missing"][3:]:
            missing_preview += f" …(+{len(info['missing'])-3})"
        print(f"  {name_cn:16s} {info['count']:>4d}  {info['status']:<24s}  {missing_preview}")

        if info["count"] == 0:
            alerts.append(f"{name_cn}（{bkt}）：无零件记录，请补充")
        elif len(info["missing"]) > len(info["missing"] + info["present"]) * 0.6:
            alerts.append(
                f"{name_cn}（{bkt}）：覆盖不全，缺 {len(info['missing'])} 项 "
                f"(如: {', '.join(info['missing'][:3])})"
            )

        bucket_report[bkt] = {
            "label": name_cn,
            "count": info["count"],
            "status": info["status"],
            "present": info["present"],
            "missing": info["missing"],
        }

    print(f"  {'-'*90}")

    if alerts:
        print(f"\n  ⚠ 覆盖告警（{len(alerts)} 条）：")
        for a in alerts:
            print(f"    • {a}")
    else:
        print(f"\n  ✓ 全部 8 桶覆盖率合格")

    return {
        "total_parts": total,
        "buckets": bucket_report,
        "alerts": alerts,
    }


# ══════════════════════════════════════════════════════════════════
#  Stage 4 — Aggregate & Bias Audit（8 桶金额汇总 + ±5% 偏差告警）
# ══════════════════════════════════════════════════════════════════

def _lookup_unit_price(
    row: dict, lib_index: dict, parts_json: dict,
    already_used_lib_ids: set | None = None,
) -> tuple[float, str]:
    """分级查价 (严格 → 模糊): 型号精确 → 规则 hint → name → standard_parts → AUX/桶兜底。

    优先级:
      0. 辅料件 → AUX 分档兜底 (aux_price)
      1. model_numbers 精确包含 (lib 已收录具体型号 → 直接命中, 不被 hint 子串拦截)
      2. 规则给的 _lib_hint 命中 lib name 子串 (lib 无具体型号时按角色分类兜底)
      3. name 完全相等 (去空格/标点)
      4. name 子串匹配
      5. standard_parts.json
      6. 桶兜底

    already_used_lib_ids: 本桶内已被"整机唯一"件命中的 lib id,
    同桶再出现时不再重复计价。
    """
    bucket = (row.get("bom_bucket") or "").strip()
    name = (row.get("name") or "").strip()
    model = (row.get("model") or "").strip()
    spec = row.get("spec", "")
    blob = f"{name} {model} {spec}"
    hint = (row.get("_lib_hint") or "").strip()

    # Tier 0: 辅料件 → 分档兜底, 不查 lib (避免误匹主件高价)
    if row.get("_is_aux"):
        return aux_price(name, spec), "aux"

    candidates = lib_index.get(bucket, [])
    used = already_used_lib_ids if already_used_lib_ids is not None else set()

    # Tier 1: model_numbers 精确包含 (只匹 model 字段, 避免 spec 描述里提到的型号误中)
    for lib_row in candidates:
        for m in (lib_row.get("model_numbers") or "").split("、"):
            m = m.strip()
            if m and m in model:
                p = _mid_cost(lib_row)
                if p:
                    used.add(lib_row["id"])
                    return p, f"lib:{lib_row['id']}(型号)"

    # Tier 2: 规则 hint → lib name 子串 (lib 没收录具体型号时, 用规则挑过的 hint 兜底分类)
    if hint:
        for lib_row in candidates:
            lname = lib_row.get("name", "")
            if lname and hint in lname:
                if lib_row["id"] in used:
                    return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}(防重)"
                p = _mid_cost(lib_row)
                if p:
                    used.add(lib_row["id"])
                    return p, f"lib:{lib_row['id']}(hint)"

    # Tier 3: name 完全相等 (去空格/标点)
    def _norm(s: str) -> str:
        return re.sub(r"[\s/+\-·]+", "", s).lower()
    name_norm = _norm(name)
    for lib_row in candidates:
        lname = lib_row.get("name", "")
        if lname and _norm(lname) == name_norm:
            if lib_row["id"] in used:
                return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}(防重)"
            p = _mid_cost(lib_row)
            if p:
                used.add(lib_row["id"])
                return p, f"lib:{lib_row['id']}"

    # Tier 4: name 子串匹配 (lib name 作为主词)
    for lib_row in candidates:
        lname = lib_row.get("name", "")
        if not lname or len(lname) < 3:
            continue
        if lname in name or lname in blob:
            if lib_row["id"] in used:
                return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}(防重)"
            p = _mid_cost(lib_row)
            if p:
                used.add(lib_row["id"])
                return p, f"lib:{lib_row['id']}(子串)"

    # Tier 5: standard_parts.json
    for group, items in parts_json.items():
        if not isinstance(items, list):
            continue
        for it in items:
            if it.get("bom_bucket") != bucket:
                continue
            it_name = it.get("name", "")
            if it_name and len(it_name) >= 3 and it_name in name:
                price = it.get("price_1k") or (it.get("price_range") or [None])[0]
                if price:
                    return float(price), f"std:{group}/{it_name}"

    # Tier 6: 桶兜底 (优先用 bom_rules 的 BUCKET_DEFAULT_PRICE, 更贴近真实)
    return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}"


def _mid_cost(row: dict) -> float | None:
    try:
        lo = float(row.get("cost_min") or 0)
        hi = float(row.get("cost_max") or 0)
    except ValueError:
        return None
    if lo == 0 and hi == 0:
        return None
    if lo == 0:
        return hi
    if hi == 0:
        return lo
    return (lo + hi) / 2


def _diagnose_bias(
    bkt: str, pct: float, target_pct: float, delta: float,
    coverage_info: dict | None, row_count: int,
) -> str:
    """根据 coverage + 偏差方向, 生成可操作的诊断建议。"""
    present = len(coverage_info.get("present", [])) if coverage_info else 0
    missing = len(coverage_info.get("missing", [])) if coverage_info else 0
    total_typical = present + missing
    coverage_ratio = present / total_typical if total_typical else 1.0

    if delta < 0:  # 偏低
        if coverage_ratio < 0.5 and missing > 0:
            miss_preview = ", ".join((coverage_info.get("missing") or [])[:3])
            return f"疑似【缺件】(覆盖 {present}/{total_typical}), 优先核查: {miss_preview}"
        return f"疑似【定价偏低】(覆盖 {present}/{total_typical} 达标, 但金额不足)，核查 components_lib.csv 中的价格"
    else:  # 偏高
        if coverage_info and row_count > total_typical * 1.5:
            return f"疑似【重复计价】({row_count} 行 vs framework 仅 {total_typical} 典型子项), 核查是否子件独立计价"
        if coverage_ratio >= 0.5:
            return f"疑似【单价偏高】或【机型溢价件】, 核查本桶 Top 3 高价行的 components_lib 价格"
        return f"覆盖不足但金额偏高, 核查是否被 default:{bkt} 兜底过多"


def stage4_aggregate_audit(
    rows: list[dict], msrp: float,
    coverage: dict | None = None,
    fill_by_framework: bool = True,
) -> dict:
    """对每行查价 → 按桶汇总 → 对照 framework 占比基准做偏差告警 + 诊断建议。

    coverage: stage3_coverage_audit 返回的 buckets dict; 传入后告警附带诊断提示
    (缺件 vs 重复计价 vs 定价偏低), 便于定位问题。
    fill_by_framework: 是否按 framework typical_items 自动补缺 (默认 True)。
                       缺件按 default_qty × lib 中位价 (lib 没收录则桶兜底价) 补入桶合计,
                       让 BOM 合计逼近真实整机成本。补件标记 [framework_fill]。
    """
    # 预建 components_lib 索引 (按桶分组)
    lib_index: dict[str, list[dict]] = {}
    for lib_row in load_lib():
        b = lib_row.get("bom_bucket", "")
        lib_index.setdefault(b, []).append(lib_row)
    parts_json = _load_standard_parts()

    bucket_totals: dict[str, float] = {k: 0.0 for k, _ in BUCKETS}
    bucket_counts: dict[str, int] = {k: 0 for k, _ in BUCKETS}
    # 每桶独立 "已用 lib id" 集合, 防止同一整机唯一件被多行重复计价
    used_by_bucket: dict[str, set] = {k: set() for k, _ in BUCKETS}
    # 聚合件: 同一 (bucket, hint) 只计一次, 下级重复行记录但 line_cost=0
    counted_aggregates: set[tuple[str, str]] = set()

    for r in rows:
        bkt = (r.get("bom_bucket") or "").strip()
        if bkt not in bucket_totals:
            continue

        # 聚合件: 整机只计一次 (复用 analyze_c33 的聚合思想)
        note = r.get("_agg_note", "")
        hint = r.get("_lib_hint", "")
        if is_aggregate(note) and hint:
            agg_key = (bkt, hint)
            if agg_key in counted_aggregates:
                r["_unit_price"] = 0
                r["_line_cost"]  = 0
                r["_price_src"]  = f"agg→[{bkt}]{hint}(已计)"
                bucket_counts[bkt] += 1
                continue
            counted_aggregates.add(agg_key)

        unit_price, src = _lookup_unit_price(
            r, lib_index, parts_json,
            already_used_lib_ids=used_by_bucket[bkt],
        )
        # 聚合件固定按 qty=1 计 (整机整体)
        qty = 1 if is_aggregate(note) else _norm_qty(r.get("qty"))
        r["_unit_price"] = round(unit_price, 2)
        r["_line_cost"]  = round(unit_price * qty, 2)
        r["_price_src"]  = src
        bucket_totals[bkt] += r["_line_cost"]
        bucket_counts[bkt] += 1

    # ── framework_fill: 按 typical_items 补缺 ───────────────────────
    # 对每桶 typical_items 检查覆盖, 缺件按 default_qty × lib 中位价补入合计
    fill_log: dict[str, list[dict]] = {k: [] for k, _ in BUCKETS}
    if fill_by_framework:
        # 用 audit_coverage 的 missing 列表作为缺件源 (与 Stage 3 一致)
        from core.bucket_framework import audit_coverage as _audit
        cov_for_fill = _audit(rows)
        for bkt, _ in BUCKETS:
            present_names = set(cov_for_fill[bkt].get("present", []))
            missing_names = set(cov_for_fill[bkt].get("missing", []))
            if not missing_names:
                continue

            # mutex_group 处理: 组内任一已 present 则跳过组内其他 missing
            # (例如双转盘/滚筒/履带三类拖布, 这台机已录履带 → 跳过双转盘和滚筒)
            items = typical_items_with_qty(bkt)
            covered_groups: set[str] = set()
            for name, _, mg in items:
                if mg and name in present_names:
                    covered_groups.add(mg)

            for name, default_qty, mutex_group in items:
                if name not in missing_names:
                    continue
                # mutex_group 命中: 跳过 (组内已有别的形态被录)
                if mutex_group and mutex_group in covered_groups:
                    fill_log[bkt].append({
                        "name": name, "qty": 0,
                        "unit": 0.0, "line": 0.0,
                        "src": f"skip:mutex({mutex_group})",
                    })
                    continue

                # 构造一个虚拟 row 走查价
                virt_row = {
                    "bom_bucket": bkt,
                    "name":       name,
                    "model":      "",
                    "spec":       "",
                    "_lib_hint":  name,  # 直接用 typical_item 名当 hint 找 lib
                    "_is_aux":    False,
                    "_agg_note":  "",
                }
                unit_price, src = _lookup_unit_price(
                    virt_row, lib_index, parts_json,
                    already_used_lib_ids=used_by_bucket[bkt],
                )
                line = round(unit_price * default_qty, 2)
                bucket_totals[bkt] += line
                bucket_counts[bkt] += 1
                fill_log[bkt].append({
                    "name": name, "qty": default_qty,
                    "unit": round(unit_price, 2), "line": line, "src": src,
                })

                # 本次 fill 命中后, 标记同组已覆盖 (避免组内 missing 重复补)
                if mutex_group:
                    covered_groups.add(mutex_group)

    grand = sum(bucket_totals.values())

    tolerance = bucket_pct_tolerance()  # 来自 framework validation_rules
    ratio_lo, ratio_hi = expected_bom_msrp_ratio()

    print(f"\n  [Stage 4] 8桶金额汇总 (查价: components_lib → standard_parts → 兜底)")
    print(f"  {'桶':16s} {'行数':>4s}  {'成本(¥)':>10s}  {'占比':>7s}  {'基准':>8s}  状态")
    print(f"  {'-'*76}")

    cov_buckets = (coverage or {}).get("buckets") if coverage else {}

    bias_alerts: list[str] = []
    bucket_money: dict[str, dict] = {}
    for bkt, name_cn in BUCKETS:
        cost = bucket_totals[bkt]
        pct = cost / grand * 100 if grand else 0
        target_pct = bucket_pct_avg(bkt) * 100
        delta = pct - target_pct
        if abs(delta) <= tolerance:
            status = "✓"
        else:
            direction = "↑偏高" if delta > 0 else "↓偏低"
            status = f"⚠ {direction} {abs(delta):.1f}%"
            diag = _diagnose_bias(
                bkt, pct, target_pct, delta,
                cov_buckets.get(bkt) if cov_buckets else None,
                bucket_counts[bkt],
            )
            bias_alerts.append(
                f"{name_cn}（{bkt}）：占比 {pct:.1f}% vs 基准 {target_pct:.0f}% "
                f"({direction} {abs(delta):.1f}%)\n      → {diag}"
            )
        print(f"  {name_cn:16s} {bucket_counts[bkt]:>4d}  {cost:>10.2f}  "
              f"{pct:>6.1f}%  {target_pct:>7.0f}%  {status}")
        bucket_money[bkt] = {
            "label": name_cn, "cost": round(cost, 2),
            "pct": round(pct, 1), "target_pct": round(target_pct, 1),
            "count": bucket_counts[bkt], "status": status,
        }

    print(f"  {'-'*76}")
    print(f"  {'整机 BOM 合计':16s} {sum(bucket_counts.values()):>4d}  {grand:>10.2f}")

    # framework_fill 明细 (让用户清楚知道哪些是真实录入、哪些是补缺估算)
    if fill_by_framework:
        # 区分: 实际补的件 vs 因 mutex_group 跳过的件
        actual_filled = [(b, it) for b, items in fill_log.items() for it in items
                         if not it["src"].startswith("skip:")]
        skipped = [(b, it) for b, items in fill_log.items() for it in items
                   if it["src"].startswith("skip:")]
        if actual_filled or skipped:
            filled_total = sum(it["line"] for _, it in actual_filled)
            print(f"\n  [framework_fill] 自动补缺 {len(actual_filled)} 件 (¥{filled_total:.2f}, "
                  f"按 typical_items × default_qty × lib 中位价)")
            if skipped:
                print(f"    跳过 {len(skipped)} 件 (mutex_group 互斥): "
                      + ", ".join(it["name"] for _, it in skipped))
            for bkt, items in fill_log.items():
                actual_items = [it for it in items if not it["src"].startswith("skip:")]
                if not actual_items:
                    continue
                bkt_cn = BUCKET_MAP.get(bkt, bkt)
                bkt_filled_total = sum(it["line"] for it in actual_items)
                print(f"    {bkt_cn} (+¥{bkt_filled_total:.2f}):")
                for it in actual_items:
                    print(f"      • {it['name']:24s} qty={it['qty']:>2d} "
                          f"× ¥{it['unit']:>5.2f} = ¥{it['line']:>6.2f}  ({it['src']})")

    ratio_alert = None
    if msrp and grand:
        bom_ratio = grand / msrp * 100
        ratio_status = "✓" if ratio_lo <= bom_ratio <= ratio_hi else "⚠"
        print(f"\n  BOM/MSRP 比例: {bom_ratio:.1f}%  "
              f"(framework 期望 {ratio_lo:.0f}-{ratio_hi:.0f}%)  {ratio_status}")
        if bom_ratio < ratio_lo:
            ratio_alert = (
                f"BOM/MSRP {bom_ratio:.1f}% 低于期望下限 {ratio_lo:.0f}%, "
                f"疑似 BOM 不完整 (Stage 1 漏项 或 components_lib 未收录)"
            )
        elif bom_ratio > ratio_hi:
            ratio_alert = (
                f"BOM/MSRP {bom_ratio:.1f}% 高于期望上限 {ratio_hi:.0f}%, "
                f"疑似零件重复计价 或 MSRP 偏低"
            )
        if ratio_alert:
            print(f"    ⚠ {ratio_alert}")

    if bias_alerts:
        print(f"\n  ⚠ 占比偏差告警（{len(bias_alerts)} 条, 容差 ±{tolerance:.0f}%）：")
        for a in bias_alerts:
            print(f"    • {a}")
    else:
        print(f"\n  ✓ 8 桶占比全部在基准 ±{tolerance:.0f}% 内")

    all_bias = bias_alerts + ([ratio_alert] if ratio_alert else [])
    return {
        "grand_total": round(grand, 2),
        "buckets_money": bucket_money,
        "bias_alerts": all_bias,
    }


# ══════════════════════════════════════════════════════════════════
#  MSRP 查询
# ══════════════════════════════════════════════════════════════════

def _load_products_db() -> dict:
    db_path = DATA_DIR / "products" / "products_db.json"
    if not db_path.exists():
        return {}
    try:
        return json.loads(db_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _lookup_msrp_from_db(model: str) -> Optional[float]:
    db = _load_products_db()
    slug = _slug(model).lower()
    for key, entry in db.items():
        if slug in key.lower() or key.lower() in slug:
            price = entry.get("retail_price_cny")
            if price:
                return float(price)
    return None


def _canonical_product_name(model: str) -> str:
    """从 products_db.json 查找规范化产品名，用于 product_source 字段统一。"""
    db = _load_products_db()
    slug = _slug(model).lower()
    best_key = None
    best_score = 0
    for key in db:
        k_slug = _slug(key).lower()
        # 精确包含匹配
        if slug == k_slug:
            return key
        if slug in k_slug or k_slug in slug:
            score = len(set(slug) & set(k_slug))
            if score > best_score:
                best_score = score
                best_key = key
    return best_key or model


def lookup_msrp_from_web(model: str) -> float:
    """多渠道搜索产品实际零售价 (国内电商 → 亚马逊海外), 查到后写入 products_db.json。"""
    print(f"  → 查询 {model} 零售价…")
    try:
        text = _run_web_agent(
            (
                "你是价格查询助手。依次在以下渠道搜索该产品的当前零售价:\n"
                "  1. 京东 (jd.com) — 国产品牌首选\n"
                "  2. 天猫/淘宝 (tmall.com / taobao.com)\n"
                "  3. 品牌官网 (如 roborock.cn / dreametech.com / switch-bot.com)\n"
                "  4. 亚马逊 (amazon.com / amazon.co.jp / amazon.de) — 海外售价\n"
                "找到最接近的商品链接, 提取当前售价。优先返回 CNY 售价。\n"
                "严格输出以下 JSON (无其他文字, 无 markdown):\n"
                '{"price_cny": 数字或null, "price_usd": 数字或null, '
                '"price_jpy": 数字或null, "price_eur": 数字或null, '
                '"source": "京东/天猫/官网/Amazon.com 等", "url": "商品链接"}'
            ),
            f"搜索 {model} 扫地机器人 / robot vacuum 的零售价, 返回 JSON。",
            max_tokens=2048,  # 留给 web_search 回合 + 解析
        )
        # 解析 JSON
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        data: dict = json.loads(m.group()) if m else {}

        price_cny = data.get("price_cny")
        price_usd = data.get("price_usd")
        price_jpy = data.get("price_jpy")
        price_eur = data.get("price_eur")
        source    = data.get("source", "")
        url       = data.get("url", "")

        # 优先级: CNY > USD > EUR > JPY
        if price_cny:
            price_cny = round(float(price_cny), 0)
            price_str = f"¥{price_cny:.0f} (原币)"
        elif price_usd:
            price_cny = round(float(price_usd) * 7.2, 0)
            price_str = f"${price_usd:.0f} → ¥{price_cny:.0f}"
        elif price_eur:
            price_cny = round(float(price_eur) * 7.8, 0)
            price_str = f"€{price_eur:.0f} → ¥{price_cny:.0f}"
        elif price_jpy:
            price_cny = round(float(price_jpy) * 0.048, 0)
            price_str = f"¥{price_jpy:.0f}(JPY) → ¥{price_cny:.0f}"
        else:
            raise ValueError(f"未找到价格 (raw 前 200 字: {text[:200]!r})")

        print(f"  ✓ 零售价: ¥{price_cny:.0f}（{price_str}  来源: {source or '-'}）")
        if url:
            print(f"  → 链接: {url}")

        _save_msrp_to_db(model, price_cny, url)
        return price_cny
    except Exception as e:
        print(f"  ⚠ 价格查询失败: {e}")
        print(f"  → 使用默认值 ¥5000 (传 --msrp 显式指定可跳过此步)")
        return 5000.0


def _save_msrp_to_db(model: str, price_cny: float, source_url: str) -> None:
    """将查到的价格和来源链接写入 products_db.json（仅新增，不覆盖已有完整条目）。"""
    db_path = DATA_DIR / "products" / "products_db.json"
    db = _load_products_db()

    slug = _slug(model).lower()
    # 找已有 key（模糊匹配）
    existing_key = None
    for key in db:
        if _slug(key).lower() == slug or slug in _slug(key).lower():
            existing_key = key
            break

    key = existing_key or model
    entry = db.get(key, {})

    # 只在价格缺失时写入，避免覆盖人工维护值
    if not entry.get("retail_price_cny"):
        entry["retail_price_cny"] = price_cny

    # 写入来源链接
    sources = entry.setdefault("data_sources", {})
    web_refs: list = sources.setdefault("web_research", [])
    if source_url and source_url not in web_refs:
        web_refs.append(source_url)
    sources["last_updated"] = str(_os.environ.get("TODAY", __import__("datetime").date.today()))

    db[key] = entry
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → 已写入 products_db.json（{key}）")


# ══════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════

def run_pipeline(model: str, msrp: float,
                 existing_csv: Optional[Path] = None) -> tuple[list[dict], dict]:
    """完整执行 Stage 0 + 4-Stage Pipeline，返回 (rows, audit_report)。

    model:           用户原始输入 (如 '云鲸逍遥003'), 用作 LLM prompt 的 model 字段
    canonical_key:   products_db key (如 'Narwal_云鲸逍遥003'), 用于内部归档/查找
    """
    # 规范化产品名 → 仅用于 product_source 内部归档, 不传给 LLM (避免 LLM 被品牌前缀误导成海外别名)
    canonical_key = _canonical_product_name(model)
    if canonical_key != model:
        print(f"  → 产品归档名: {model!r} (LLM 用) | {canonical_key!r} (CSV product_source 列)")
    slug = _slug(canonical_key)

    # Stage 0: 加载 FCC 上游（fetch_fcc.py find+ocr 产出，有则用，无则静默跳过）
    fcc_rows = load_fcc_rows(slug)

    # Stage 1: Discovery (LLM 用 model 原名, 不用 canonical_key)
    if existing_csv and existing_csv.exists():
        rows = load_csv(existing_csv)
        print(f"  ✓ 加载现有 CSV: {existing_csv.name}（{len(rows)} 条）")
    else:
        rows = stage1_discovery(model, msrp, fcc_rows=fcc_rows)

    # 后续 product_source 列填 canonical_key (内部归档统一)
    model = canonical_key

    # FCC 优先合并：FCC 行覆盖同 (bucket, name) 的 web 行
    if fcc_rows:
        rows = _merge_fcc_first(fcc_rows, rows)

    # Stage 2: SoC Heuristic Enrichment (推导 PMIC/RAM/ROM 伴随件)
    rows = stage2_heuristic_enrichment(rows)

    # 桶名归一化 (兜底: LLM 偶尔自创命名)
    rows = normalize_buckets(rows)

    # 规则二次归桶 (复用 analyze_c33 的 KEYWORD_RULES + 聚合标记 + 辅料识别)
    rows = apply_rules_overlay(rows)

    # Stage 3: Coverage Audit (对照 framework typical_items 报缺失关键子项)
    coverage = stage3_coverage_audit(rows)

    # Stage 4: Aggregate & Bias Audit (8 桶金额 + ±5% 占比偏差告警 + coverage 诊断)
    money = stage4_aggregate_audit(rows, msrp, coverage=coverage)

    return rows, {
        "msrp": msrp,
        "total_parts": len(rows),
        "coverage": coverage,
        "money": money,
        "alerts": coverage["alerts"] + money["bias_alerts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="拆机 BOM 生成器 — 4-Stage Pipeline (对齐 core/bom_8bucket_framework.json)")
    parser.add_argument("model", nargs="?", help="机型名称，如 '石头G30S Pro'")
    parser.add_argument("--msrp",    type=float, help="建议零售价（元），不传则自动查询")
    parser.add_argument("--csv",     type=Path,  help="指定现有 CSV 路径（跳过 Stage 1）")
    parser.add_argument("--out",     type=Path,  help="输出 CSV 路径（默认 data/teardowns/{slug}_{YYYYMMDD}_teardown.csv）")
    args = parser.parse_args()

    if not args.model and not args.csv:
        parser.error("请提供机型名称或 --csv 路径")

    # 从 --csv 反推机型名: 同时剥掉可能的 _YYYYMMDD 日期后缀
    if args.model:
        model = args.model
    else:
        stem = args.csv.stem.replace("_teardown", "")
        stem = re.sub(r"_\d{8}$", "", stem)   # 剥日期
        model = stem.replace("_", " ")
    slug  = _slug(model)

    # 解析 MSRP
    msrp = args.msrp or _lookup_msrp_from_db(model)
    if not msrp:
        msrp = lookup_msrp_from_web(model)
    msrp = msrp or 5000.0

    # 输出路径: 默认带今天日期, 便于版本追溯
    today_tag = __import__("datetime").date.today().strftime("%Y%m%d")
    csv_out = args.out or TEARDOWN_DIR / f"{slug}_{today_tag}_teardown.csv"

    print(f"\n机型: {model}  |  零售价: {msrp:.0f} 元  |  输出: {csv_out.name}")
    print("=" * 60)

    # 执行 Pipeline
    try:
        rows, audit = run_pipeline(
            model=model,
            msrp=msrp,
            existing_csv=args.csv,
        )
    except RuntimeError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    # 保存 CSV
    save_csv(rows, csv_out, model)
    if rows:
        print(f"\n✓ 写出 → {csv_out}\n")
        # 打印汇总
        print(f"总计 {len(rows)} 条零件记录 | BOM 合计 ¥{audit['money']['grand_total']:.2f}")
        if audit["alerts"]:
            print(f"⚠ {len(audit['alerts'])} 条告警 "
                  f"(覆盖 {len(audit['coverage']['alerts'])} / 占比偏差 {len(audit['money']['bias_alerts'])}), "
                  f"请核实后人工核准入库")


if __name__ == "__main__":
    main()
