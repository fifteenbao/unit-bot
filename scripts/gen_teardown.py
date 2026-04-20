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
DATA_DIR     = ROOT / "data"
TEARDOWN_DIR = DATA_DIR / "teardowns"
PARTS_FILE    = DATA_DIR / "standard_parts.json"
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
    "spec", "manufacturer", "unit_price", "qty", "confidence", "product_source",
]

# ── FCC 厂商代码 ───────────────────────────────────────────────────
BRAND_FCC_CODE: dict[str, str] = {
    "石头":     "2AN2O",
    "roborock": "2AN2O",
    "云鲸":     "2ARZZ",
    "narwal":   "2ARZZ",
    "追觅":     "2AX54",
    "dreame":   "2AX54",
    "科沃斯":   "2A6HE",
    "ecovacs":  "2A6HE",
}


def _fcc_hint(model: str) -> str:
    low = model.lower()
    for keyword, code in BRAND_FCC_CODE.items():
        if keyword in low:
            brand_map = {
                "石头": "Roborock", "roborock": "Roborock",
                "云鲸": "Narwal",   "narwal":   "Narwal",
                "追觅": "Dreame",   "dreame":   "Dreame",
                "科沃斯": "Ecovacs","ecovacs":  "Ecovacs",
            }
            brand = brand_map.get(keyword)
            global_name = None
            try:
                from core.model_aliases import cn_to_global, find_alias
                sys.path.insert(0, str(ROOT))
                global_name = cn_to_global(model, brand)
                if not global_name:
                    hits = find_alias(model, brand, top_k=1)
                    if hits and hits[0].score >= 0.5:
                        global_name = hits[0].global_model
            except Exception:
                pass
            search_name = global_name or model
            return (
                f"FCC grantee code: {code}\n"
                f"- 品牌设备列表: https://fccid.io/{code}\n"
                f"- 建议搜索型号: 「{search_name}」"
                + (f"（国内型号 {model} 的海外对应款）" if global_name else "")
                + "\n- 进入最相近型号，用 web_fetch 抓取 Internal Photos 和 Block Diagram\n"
                "- 从照片识别 PCB 芯片丝印（SoC/MCU/Wi-Fi/PMIC），从框图提取系统架构"
            )
    return ""


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
#  Claude API 工具调用循环
# ══════════════════════════════════════════════════════════════════

SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209",  "name": "web_fetch"},
]


def _run_web_agent(system: str, user: str, max_tokens: int = 8192) -> str:
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user}]

    while True:
        resp = client.messages.create(
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=SERVER_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            return "\n".join(texts)

        if resp.stop_reason == "pause_turn":
            continue

        texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        if texts:
            return "\n".join(texts)
        raise RuntimeError(f"意外的 stop_reason: {resp.stop_reason}")


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
    "你是扫地机器人硬件 BOM 成本分析专家，熟悉各品牌拆机报告、"
    "主要芯片厂商（全志、瑞芯微、比特大陆、TI、ST、InvenSense）及元件市场价。"
    "擅长从 FCC ID.io 内部照片中识别 PCB 芯片丝印和器件型号。"
    "数据源优先级：FCC ID.io 内部照片 > MyFixGuide拆机 > 知乎Robot森 > 我爱音频网 > 规格评测页。"
    "严格按照指定 JSON 格式输出，不要输出任何额外文字。"
)

_DISCOVERY_PROMPT = """\
请为 **{model}**（建议零售价约 {msrp} 元）从多个数据源生成完整拆机 BOM 清单。

**操作步骤（按顺序执行）**

1. **FCC 认证文件**（优先级最高）
{fcc_hint}
   - 若品牌未收录，web_search "{model} FCC ID" 获取认证编号后再抓取

2. **拆机报告**
   - web_search: "{model} site:myfixguide.com"
   - web_search: "{model} 拆机报告 PCB 芯片 知乎"
   - web_search: "{model} teardown internals disassembly"

3. **蓝牙SIG认证**（可确认芯片型号）
   - web_search: "{model} site:bluetooth.com/specifications/assigned-numbers"
   - web_search: "{model} bluetooth qualified"

4. **规格/评测补充**
   - web_search: "{model} 规格参数 SoC CPU 雷达型号 传感器"

5. **综合以上来源**，输出下方 JSON

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
    "unit_price": 0,
    "qty": 1,
    "confidence": "teardown"
  }}
]

confidence 说明：
- teardown：从 FCC 内部照片/拆机照片直接识别（最高可信）
- web：从网络评测/规格页确认
- estimate：行业基准估算（无直接证据）
- inferred：基于现有信息推断

**目标**：覆盖全部 8 个桶，每桶至少 3 个主要零件，unit_price 留 0（后续流水线补全）。\
"""


def stage1_discovery(model: str, msrp: float) -> list[dict]:
    print(f"  [Stage 1] 多源调研 {model}…")
    fcc_hint = _fcc_hint(model)
    if fcc_hint:
        print("  → 检测到 FCC 代码，优先抓取 FCC ID.io 内部照片")

    prompt = _DISCOVERY_PROMPT.format(
        model=model,
        msrp=int(msrp),
        fcc_hint=fcc_hint if fcc_hint else "   （品牌未收录，跳过 FCC，直接进行步骤2）",
    )
    text = _run_web_agent(_DISCOVERY_SYSTEM, prompt, max_tokens=8192)
    rows = _extract_json_array(text)

    for r in rows:
        r["product_source"] = model
        for key in CSV_FIELDS:
            r.setdefault(key, "")
        r["unit_price"] = _norm_price(r.get("unit_price"))
        r["qty"]        = _norm_qty(r.get("qty"))

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

        # PMIC
        pmic = rules.get("pmic")
        if pmic and ("compute_electronics", pmic.upper()) not in existing_models and "pmic" not in existing_names:
            rows.append({
                "bom_bucket": "compute_electronics", "section": "主板",
                "name": "PMIC", "model": pmic, "type": "电源管理",
                "spec": f"配套 {soc_model} 多路 DC-DC+LDO",
                "manufacturer": "瑞芯微" if pmic.startswith("RK") else "",
                "unit_price": 0.0, "qty": 1, "confidence": "inferred",
                "product_source": row.get("product_source", ""),
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
                "unit_price": 0.0, "qty": 1, "confidence": "inferred",
                "product_source": row.get("product_source", ""),
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
                "unit_price": 0.0, "qty": 1, "confidence": "inferred",
                "product_source": row.get("product_source", ""),
            })
            existing_names.add("rom")
            added += 1

        # AI 授权（RK3588S 等高端 SoC）
        if rules.get("ai_license") and "ai授权" not in existing_names and "算法版税" not in existing_names:
            rows.append({
                "bom_bucket": "mva_software", "section": "软件授权",
                "name": "AI算法授权", "model": "", "type": "软件",
                "spec": f"NPU 算法版税（{soc_model}平台）",
                "manufacturer": "", "unit_price": 0.0, "qty": 1,
                "confidence": "inferred",
                "product_source": row.get("product_source", ""),
            })
            existing_names.add("ai授权")
            added += 1

    if added:
        print(f"  [Stage 2] Heuristic 推导补充 {added} 条伴随件")
    else:
        print(f"  [Stage 2] Heuristic 推导：无需补充")
    return rows


# ══════════════════════════════════════════════════════════════════
#  Stage 3 — Price Lookup（components_lib.csv → standard_parts.json）
#
#  价格不从网络查询，统一从人工维护的库表中匹配：
#    1. components_lib.csv（cost_min/cost_max，权威来源）
#    2. standard_parts.json（price_1k × discount_factor，基准 fallback）
#  两者都未命中则 unit_price 保留 0，confidence 标注 "estimate"。
# ══════════════════════════════════════════════════════════════════

def _load_comp_lib() -> list[dict]:
    """读取 components_lib.csv，返回行列表（字段: id/name/model_numbers/cost_min/cost_max/bom_bucket 等）"""
    if not COMP_LIB_FILE.exists():
        return []
    with open(COMP_LIB_FILE, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _match_comp_lib(row: dict, lib_rows: list[dict]) -> Optional[dict]:
    """
    按优先级在 components_lib.csv 中查找匹配行：
      1. model_numbers 字段包含 row["model"]（型号精确命中）
      2. name 字段与 row["name"] 相似 + bom_bucket 相同
      3. name 字段与 row["name"] 相似（跨桶模糊匹配）
    返回匹配行或 None。
    """
    rmodel  = (row.get("model") or "").strip().lower()
    rname   = (row.get("name")  or "").strip().lower()
    rbucket = (row.get("bom_bucket") or "").strip()

    best: Optional[dict] = None
    best_score = 0

    for lib in lib_rows:
        lmodels = (lib.get("model_numbers") or "").lower()
        lname   = (lib.get("name") or "").strip().lower()
        lbucket = (lib.get("bom_bucket") or "").strip()

        score = 0
        # 型号命中（最高优先级）
        if rmodel and rmodel in lmodels:
            score = 100
        # 名称子串命中 + 同桶
        elif rname and (rname in lname or lname in rname):
            score = 60 + (20 if lbucket == rbucket else 0)
        # 名称首词命中
        elif rname and lname:
            rword = rname.split()[0] if rname.split() else rname
            lword = lname.split()[0] if lname.split() else lname
            if len(rword) >= 2 and rword == lword:
                score = 30 + (10 if lbucket == rbucket else 0)

        if score > best_score:
            best_score = score
            best = lib

    return best if best_score >= 30 else None


def stage3_price_lookup(rows: list[dict]) -> list[dict]:
    """
    从 components_lib.csv（权威）和 standard_parts.json（fallback）查价，
    填入 unit_price。不调用任何网络 API。
    """
    lib_rows   = _load_comp_lib()
    parts      = _load_standard_parts()
    disc_factors = parts.get("discount_factors", {})

    # 从 standard_parts 展开所有条目列表
    std_entries: list[dict] = []
    for v in parts.values():
        if isinstance(v, list):
            std_entries.extend(v)

    hit_csv = hit_std = miss = 0

    for r in rows:
        if _norm_price(r.get("unit_price")) > 0:
            continue  # 已有价格（Stage 1 直接给出的），保留

        # ── 优先：components_lib.csv ──────────────────────────────
        lib_match = _match_comp_lib(r, lib_rows)
        if lib_match:
            cost_min = _norm_price(lib_match.get("cost_min"))
            cost_max = _norm_price(lib_match.get("cost_max"))
            if cost_min or cost_max:
                # 取中点；若只有单侧则用该值
                if cost_min and cost_max:
                    r["unit_price"] = round((cost_min + cost_max) / 2, 2)
                else:
                    r["unit_price"] = cost_min or cost_max
                if not r.get("manufacturer") and lib_match.get("suppliers"):
                    r["manufacturer"] = lib_match["suppliers"].split("/")[0].strip()
                # 置信度升级（来自人工维护的 CSV）
                r["confidence"] = lib_match.get("confidence") or "web"
                hit_csv += 1
                continue

        # ── Fallback：standard_parts.json ────────────────────────
        rmodel  = (r.get("model") or "").strip().upper()
        rname   = (r.get("name")  or "").strip().lower()
        rspec   = (r.get("spec")  or "").strip().lower()
        bucket  = r.get("bom_bucket", "")

        best_std: Optional[dict] = None
        for entry in std_entries:
            emodel = (entry.get("model") or "").strip().upper()
            ename  = (entry.get("name")  or "").strip().lower()
            espec  = (entry.get("spec")  or "").strip().lower()

            if rmodel and emodel and rmodel == emodel:
                best_std = entry
                break
            if ename and (ename in rname or rname in ename):
                if not best_std:
                    best_std = entry
                if espec and any(kw.strip() in rspec for kw in espec.split("，")[:2] if len(kw.strip()) > 1):
                    best_std = entry
                    break

        if best_std and best_std.get("price_1k"):
            factor_key = (
                "chip"      if bucket == "compute_electronics" else
                "sensor"    if bucket == "perception"          else
                "motor"     if bucket in ("power_motion", "cleaning", "dock_station") else
                "battery"   if bucket == "energy"             else
                "structure" if bucket == "structure_cmf"      else
                "mva"
            )
            factor = disc_factors.get(factor_key, 1.0)
            r["unit_price"] = round(best_std["price_1k"] * factor, 2)
            if not r.get("manufacturer") and best_std.get("manufacturer"):
                r["manufacturer"] = best_std["manufacturer"]
            if r.get("confidence") in ("", "estimate"):
                r["confidence"] = "estimate"
            hit_std += 1
        else:
            miss += 1

    total = len(rows)
    print(f"  [Stage 3] 价格查表：CSV命中 {hit_csv}，基准命中 {hit_std}，未匹配 {miss}（共 {total} 条）")
    if miss:
        print(f"  → {miss} 条 unit_price=0，请在 components_lib.csv 补充后重新运行")
    return rows


# ══════════════════════════════════════════════════════════════════
#  Stage 4 — Aggregate & Audit（8桶汇总 + ±5% 偏差告警）
# ══════════════════════════════════════════════════════════════════

def stage4_aggregate_audit(rows: list[dict], msrp: float) -> dict:
    """
    汇总各桶成本，与理论区间对比，输出告警。
    返回 audit_report dict（同时打印到控制台）。
    """
    bom_rate = 0.50 if msrp >= 4000 else 0.58 if msrp < 2000 else 0.52
    total_theory = msrp * bom_rate

    bucket_totals: dict[str, float] = {k: 0.0 for k, _ in BUCKETS}
    for r in rows:
        bkt = r.get("bom_bucket", "").strip()
        total = _norm_price(r.get("unit_price")) * _norm_qty(r.get("qty"))
        if bkt in bucket_totals:
            bucket_totals[bkt] += total

    total_actual = sum(bucket_totals.values())

    print(f"\n  [Stage 4] 8桶成本汇总（理论总额 ¥{total_theory:.0f}，实际 ¥{total_actual:.0f}）")
    print(f"  {'桶':16s} {'理论区间':14s} {'实际':8s} {'占比':6s} {'状态'}")
    print(f"  {'-'*60}")

    alerts = []
    bucket_report = {}
    for bkt, label in BUCKETS:
        actual  = bucket_totals.get(bkt, 0.0)
        lo_pct, hi_pct = BUCKET_THEORY.get(bkt, (0, 0))
        lo = total_theory * lo_pct
        hi = total_theory * hi_pct
        pct = actual / total_theory if total_theory else 0

        if actual == 0:
            status = "⚠ 缺数据"
            alerts.append(f"{label}（{bkt}）：无零件数据，桶合计为 ¥0")
        elif actual < lo * 0.95:
            diff_pct = (lo - actual) / lo * 100
            status = f"↓ 偏低 {diff_pct:.0f}%"
            alerts.append(f"{label}：¥{actual:.0f} 低于理论下限 ¥{lo:.0f}（偏低 {diff_pct:.0f}%），可能漏件或价格偏低")
        elif actual > hi * 1.05:
            diff_pct = (actual - hi) / hi * 100
            status = f"↑ 偏高 {diff_pct:.0f}%"
            alerts.append(f"{label}：¥{actual:.0f} 高于理论上限 ¥{hi:.0f}（偏高 {diff_pct:.0f}%），请核实是否包含重复件")
        else:
            status = "✓ 正常"

        print(f"  {label:16s} ¥{lo:.0f}~{hi:.0f:6.0f}   ¥{actual:6.0f}  {pct:.0%}  {status}")
        bucket_report[bkt] = {
            "label": label,
            "actual_cny": round(actual, 2),
            "theory_range": [round(lo, 2), round(hi, 2)],
            "pct": round(pct * 100, 1),
            "status": status,
        }

    print(f"  {'-'*60}")
    print(f"  {'合计':16s} ¥{total_theory:.0f}        ¥{total_actual:.0f}")

    if alerts:
        print(f"\n  [Stage 4] ⚠ 告警（{len(alerts)} 条）：")
        for a in alerts:
            print(f"    • {a}")

    return {
        "msrp": msrp,
        "bom_rate": bom_rate,
        "total_theory_cny": round(total_theory, 2),
        "total_actual_cny": round(total_actual, 2),
        "buckets": bucket_report,
        "alerts": alerts,
    }


# ══════════════════════════════════════════════════════════════════
#  MSRP 查询
# ══════════════════════════════════════════════════════════════════

def _lookup_msrp_from_db(model: str) -> Optional[float]:
    db_path = DATA_DIR / "products_db.json"
    if not db_path.exists():
        return None
    try:
        db = json.loads(db_path.read_text(encoding="utf-8"))
        slug = _slug(model).lower()
        for key, entry in db.items():
            if slug in key.lower() or key.lower() in slug:
                price = entry.get("retail_price_cny")
                if price:
                    return float(price)
    except Exception:
        pass
    return None


def lookup_msrp_from_web(model: str) -> float:
    print(f"  → 查询 {model} 零售价…")
    try:
        text = _run_web_agent(
            "你是价格查询助手，只输出一个纯数字（人民币元），不要任何其他文字。",
            f"请搜索 {model} 的中国官方建议零售价（CNY），只返回数字。",
            max_tokens=256,
        )
        price = float(re.search(r"\d[\d,\.]*", text.replace(",", "")).group())
        print(f"  ✓ 零售价: {price:.0f} 元")
        return price
    except Exception as e:
        print(f"  ⚠ 价格查询失败: {e}，使用默认值 5000 元")
        return 5000.0


# ══════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════

def run_pipeline(model: str, msrp: float,
                 existing_csv: Optional[Path] = None) -> tuple[list[dict], dict]:
    """完整执行 4-Stage Pipeline，返回 (rows, audit_report)。"""
    # Stage 1: Discovery
    if existing_csv and existing_csv.exists():
        rows = load_csv(existing_csv)
        print(f"  ✓ 加载现有 CSV: {existing_csv.name}（{len(rows)} 条）")
    else:
        rows = stage1_discovery(model, msrp)

    # Stage 2: Heuristic Enrichment
    rows = stage2_heuristic_enrichment(rows)

    # Stage 3: Price Lookup（components_lib.csv → standard_parts.json）
    rows = stage3_price_lookup(rows)

    # Stage 4: Aggregate & Audit
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
    if not msrp and not args.no_enrich:
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
    print(f"总计 {len(rows)} 条零件，BOM 估算 ¥{audit['total_actual_cny']:.0f} / 零售价 ¥{msrp:.0f}")
    if audit["alerts"]:
        print(f"⚠ {len(audit['alerts'])} 条告警，请核实后人工核准入库")


if __name__ == "__main__":
    main()
