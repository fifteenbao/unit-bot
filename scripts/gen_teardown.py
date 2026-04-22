#!/usr/bin/env python3
"""
拆机 BOM 生成器 — 4-Stage Pipeline

职责：爬取元器件型号 + 判断置信度
价格来源：components_lib.csv（人工维护，权威来源）→ standard_parts.json（基准 fallback）
不调用 API 查价；定价更新请维护 data/lib/components_lib.csv

用法：
    python scripts/gen_teardown.py "石头G30S Pro"
    python scripts/gen_teardown.py "科沃斯X8 Pro" --msrp 6999
    python scripts/gen_teardown.py --csv data/teardowns/xxx.csv "机型名"

输出：data/teardowns/{model_slug}_teardown.csv
Pipeline：Stage 1 Discovery → Stage 2 Heuristic Enrichment → Stage 3 Price Lookup → Stage 4 Aggregate & Audit
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

# ── BOM 8桶 ───────────────────────────────────────────────────────
BUCKETS = [
    ("compute_electronics", "计算/电子"),
    ("perception",          "感知"),
    ("power_motion",        "驱动运动"),
    ("cleaning",            "清洁"),
    ("energy",              "能源/电池"),
    ("dock_station",        "基站"),
    ("structure_cmf",       "结构CMF"),
    ("mva_software",        "MVA+软件"),
]
BUCKET_MAP = {k: v for k, v in BUCKETS}

# 旗舰机各桶理论占比区间（BOM总额的百分比）
BUCKET_THEORY = {
    "compute_electronics": (0.10, 0.12),
    "perception":          (0.10, 0.13),
    "power_motion":        (0.10, 0.12),
    "cleaning":            (0.13, 0.17),
    "energy":              (0.07, 0.09),
    "dock_station":        (0.15, 0.25),
    "structure_cmf":       (0.10, 0.13),
    "mva_software":        (0.09, 0.13),
}

CSV_FIELDS = [
    "bom_bucket", "section", "name", "model", "type",
    "spec", "manufacturer", "qty", "source_url", "updated_at", "product_source",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    for r in rows:
        r.setdefault("product_source", model)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def find_csv(model: str) -> Optional[Path]:
    slug = _slug(model)
    exact = TEARDOWN_DIR / f"{slug}_teardown.csv"
    if exact.exists():
        return exact
    for p in sorted(TEARDOWN_DIR.glob("*_teardown*.csv")):
        if slug.lower() in p.name.lower() or p.stem.lower().startswith(slug.lower()[:6]):
            return p
    return None


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
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user}]

    while True:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=_ANTHROPIC_SERVER_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason in ("end_turn", "pause_turn"):
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            return "\n".join(texts)

        texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        if texts:
            return "\n".join(texts)
        raise RuntimeError(f"意外的 stop_reason: {resp.stop_reason}")


def _run_web_agent_openai(system: str, user: str, max_tokens: int = 8192) -> str:
    import openai as _openai
    import httpx as _httpx

    client = _openai.OpenAI(api_key=_AIHUBMIX_KEY, base_url=_AIHUBMIX_BASE)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    while True:
        resp = client.chat.completions.create(
            model=_AIHUBMIX_MODEL,
            max_completion_tokens=max_tokens,
            messages=messages,
            tools=_OPENAI_SERVER_TOOLS,
            tool_choice="auto",
        )
        choice  = resp.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_unset=False))

        if choice.finish_reason == "stop" or not message.tool_calls:
            return message.content or ""

        # 处理 web_search 工具调用（aihubmix 会直接返回结果，无需本地执行）
        tool_results = []
        for tc in message.tool_calls:
            tool_results.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      f"[web_search 已由服务端执行，结果已包含在上下文中]",
            })
        messages.extend(tool_results)


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

**操作步骤（按顺序执行）**

1. **拆机报告**
   - web_search: "{model} site:myfixguide.com"
   - web_search: "{model} 拆机报告 PCB 芯片 知乎"
   - web_search: "{model} teardown internals disassembly"

2. **蓝牙SIG认证**（可确认芯片型号）
   - web_search: "{model} bluetooth qualified chip"

3. **规格/评测补充**
   - web_search: "{model} 规格参数 SoC CPU 雷达型号 传感器"

4. **综合以上来源**，输出下方 JSON

---

**8个BOM桶说明**
- compute_electronics: SoC/CPU、NPU、MCU、RAM/ROM、Wi-Fi/BT、PMIC、马达驱动IC、充电IC、被动元件、PCB
- perception: 激光雷达、结构光/ToF、IMU、下视/沿墙/碰撞传感器、超声波
- power_motion: 风机、驱动轮电机+齿轮箱+减震、底盘升降电机及机构
- cleaning: 拖布盘/电机、水泵、机身水箱、滚刷/边刷本体、管路密封
- energy: 电池包（电芯+BMS）
- dock_station: 集尘电机、清洗水泵、加热烘干模块、基站PCB、基站外壳/水箱
- structure_cmf: 机身上盖/底盘注塑、保险杠、万向轮、尘盒、喷涂/CMF、模具摊销
- mva_software: 组装人工、SLAM算法版税、包装材料、QA出厂检测、OS/系统授权

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

**目标**：覆盖全部 8 个桶，每桶至少 3 个主要零件。\
"""



def stage1_discovery(model: str, msrp: float) -> list[dict]:
    print(f"  [Stage 1] 多源调研 {model}…")
    prompt = _DISCOVERY_PROMPT.format(model=model, msrp=int(msrp))
    text = _run_web_agent(_DISCOVERY_SYSTEM, prompt, max_tokens=8192)
    rows = _extract_json_array(text)

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
#  Stage 3 — Coverage Audit（8桶零件覆盖度检查）
# ══════════════════════════════════════════════════════════════════

def stage4_aggregate_audit(rows: list[dict], msrp: float) -> dict:
    """
    按桶统计零件数量，检查覆盖缺口。不做金额汇总。
    返回 audit_report dict（同时打印到控制台）。
    """
    bucket_counts: dict[str, int] = {k: 0 for k, _ in BUCKETS}
    for r in rows:
        bkt = r.get("bom_bucket", "").strip()
        if bkt in bucket_counts:
            bucket_counts[bkt] += 1

    total = len(rows)
    print(f"\n  [Stage 3] 8桶零件覆盖（共 {total} 条）")
    print(f"  {'桶':16s} {'零件数':6s} {'状态'}")
    print(f"  {'-'*40}")

    alerts = []
    bucket_report = {}
    for bkt, label in BUCKETS:
        count = bucket_counts.get(bkt, 0)
        if count == 0:
            status = "⚠ 无数据"
            alerts.append(f"{label}（{bkt}）：无零件记录，请补充")
        elif count < 3:
            status = f"△ 较少（{count}条）"
        else:
            status = f"✓ {count} 条"

        print(f"  {label:16s} {count:4d}   {status}")
        bucket_report[bkt] = {"label": label, "count": count, "status": status}

    print(f"  {'-'*40}")

    if alerts:
        print(f"\n  ⚠ 缺口告警（{len(alerts)} 条）：")
        for a in alerts:
            print(f"    • {a}")

    return {
        "msrp": msrp,
        "total_parts": total,
        "buckets": bucket_report,
        "alerts": alerts,
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
    """从亚马逊搜索产品实际售价，查到后自动写入 products_db.json。"""
    print(f"  → 查询 {model} 零售价…")
    try:
        text = _run_web_agent(
            (
                "你是价格查询助手。请在亚马逊（amazon.com 或 amazon.co.jp）搜索该产品，"
                "找到最接近的商品列表页或商品详情页，提取当前售价。\n"
                "只输出以下 JSON 格式，不要任何其他文字：\n"
                '{"price_usd": 数字或null, "price_jpy": 数字或null, "url": "亚马逊链接"}'
            ),
            f"请在亚马逊搜索：{model} robot vacuum，返回售价和链接。",
            max_tokens=512,
        )
        # 解析 JSON
        m = re.search(r"\{[^}]+\}", text, re.DOTALL)
        data: dict = json.loads(m.group()) if m else {}

        price_usd = data.get("price_usd")
        price_jpy = data.get("price_jpy")
        amazon_url = data.get("url", "")

        # 换算成人民币（粗略汇率）
        if price_usd:
            price_cny = round(float(price_usd) * 7.2, 0)
            price_str = f"${price_usd:.0f} → ¥{price_cny:.0f}"
        elif price_jpy:
            price_cny = round(float(price_jpy) * 0.048, 0)
            price_str = f"¥{price_jpy:.0f}(JPY) → ¥{price_cny:.0f}"
        else:
            raise ValueError("未找到价格")

        print(f"  ✓ 零售价: {price_cny:.0f} 元（{price_str}）")
        if amazon_url:
            print(f"  → 来源: {amazon_url}")

        # 自动写入 products_db.json
        _save_msrp_to_db(model, price_cny, amazon_url)

        return price_cny
    except Exception as e:
        print(f"  ⚠ 价格查询失败: {e}，使用默认值 5000 元")
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
    """完整执行 4-Stage Pipeline，返回 (rows, audit_report)。"""
    # 规范化产品名（确保 product_source 与 products_db key 一致）
    canonical = _canonical_product_name(model)
    if canonical != model:
        print(f"  → 产品名规范化: {model!r} → {canonical!r}")
    model = canonical

    # Stage 1: Discovery
    if existing_csv and existing_csv.exists():
        rows = load_csv(existing_csv)
        print(f"  ✓ 加载现有 CSV: {existing_csv.name}（{len(rows)} 条）")
    else:
        rows = stage1_discovery(model, msrp)

    # Stage 2: Heuristic Enrichment
    rows = stage2_heuristic_enrichment(rows)

    # Stage 3: Coverage Audit
    audit = stage4_aggregate_audit(rows, msrp)

    return rows, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="拆机 BOM 生成器 — 4-Stage Pipeline")
    parser.add_argument("model", nargs="?", help="机型名称，如 '石头G30S Pro'")
    parser.add_argument("--msrp",    type=float, help="建议零售价（元），不传则自动查询")
    parser.add_argument("--csv",     type=Path,  help="指定现有 CSV 路径（跳过 Stage 1）")
    parser.add_argument("--out",     type=Path,  help="输出 CSV 路径（默认 data/teardowns/{slug}_teardown.csv）")
    args = parser.parse_args()

    if not args.model and not args.csv:
        parser.error("请提供机型名称或 --csv 路径")

    model = args.model or args.csv.stem.replace("_teardown", "").replace("_", " ")
    slug  = _slug(model)

    # 解析 MSRP
    msrp = args.msrp or _lookup_msrp_from_db(model)
    if not msrp:
        msrp = lookup_msrp_from_web(model)
    msrp = msrp or 5000.0

    # 输出路径
    csv_out = args.out or TEARDOWN_DIR / f"{slug}_teardown.csv"

    print(f"\n机型: {model}  |  零售价: {msrp:.0f} 元  |  输出: {csv_out.name}")
    print("=" * 60)

    # 执行 Pipeline
    rows, audit = run_pipeline(
        model=model,
        msrp=msrp,
        existing_csv=args.csv,
    )

    # 保存 CSV
    save_csv(rows, csv_out, model)
    print(f"\n✓ 写出 → {csv_out}\n")

    # 打印汇总
    print(f"总计 {len(rows)} 条零件记录")
    if audit["alerts"]:
        print(f"⚠ {len(audit['alerts'])} 条桶覆盖告警，请核实后人工核准入库")


if __name__ == "__main__":
    main()
