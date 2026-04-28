#!/usr/bin/env python3
"""
FCC 独立采集模块（fccid.io + 本地 PDF 缓存 + 视觉 OCR）

两步工作流：
  Step 1 · fcc_find — 查找 FCC ID，列出文档链接（不下载），供人工确认后进行下一步
  Step 2 · fcc_ocr  — 下载目标 PDF 并用视觉模型 OCR，识别 PCB 芯片丝印

目录结构：
  data/teardowns/fcc/{slug}/
    links.json        ← fcc_find 产出：FCC ID + 文档链接列表
    {fcc_id}.json     ← fcc_ocr 产出：OCR 识别结果
    latest.json       ← 同上，快捷入口供 gen_teardown.py 读取
    pdfs/             ← 下载的 PDF 缓存

用法：
    # Step 1：查找 FCC 文档链接
    python scripts/fetch_fcc.py find "石头G30S Pro"
    python scripts/fetch_fcc.py find "科沃斯X8 Pro" --fcc-id 2A6HE-DEX8PRO

    # Step 2：OCR 识别（需先 find，也可直接指定 fcc-id 跳过 find）
    python scripts/fetch_fcc.py ocr "石头G30S Pro"
    python scripts/fetch_fcc.py ocr "石头G30S Pro" --fcc-id 2AN2O-G30SPRO --force
    AIHUBMIX_API_KEY=xxx AIHUBMIX_MODEL=gpt-4o python scripts/fetch_fcc.py ocr "石头G30S Pro"

    # 兼容旧用法（等价于 find + ocr）
    python scripts/fetch_fcc.py "石头G30S Pro"
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT    = Path(__file__).parent.parent
FCC_DIR = ROOT / "data" / "teardowns" / "fcc"

sys.path.insert(0, str(ROOT))

# ── 品牌 FCC Grantee Code ──────────────────────────────────────────
# Grantee Code 是 FCC ID 的前 3~5 位，唯一标识申请品牌/公司
BRAND_FCC_CODE: dict[str, str] = {
    "石头":         "2AN2O",  # Roborock (Beijing Roborock Technology)
    "roborock":     "2AN2O",
    "云鲸":         "2ARZZ",  # Narwal (Shanghai Gaussian Robotics)
    "narwal":       "2ARZZ",
    "追觅":         "2AX54",  # Dreame Technology
    "dreame":       "2AX54",
    "科沃斯":       "2A6HE",  # Ecovacs Robotics
    "ecovacs":      "2A6HE",
    "卧安":         "2AKXB",  # 卧安科技 SwitchBot (Woan Technology Shenzhen)
    "switchbot":    "2AKXB",
    "woan":         "2AKXB",
    "杉川":         "2A9W4",  # 杉川机器人 (Shenzhen 3irobotics Co., Ltd.)
    "3irobotics":   "2A9W4",
    "安克":         "2AOKB",  # 安克创新 Eufy / Anker Innovations
    "eufy":         "2AOKB",
    "小米":         "2AFZZ",  # 小米 Xiaomi
    "xiaomi":       "2AFZZ",
    "必胜":         "2AS9L",  # Bissell
    "bissell":      "2AS9L",
    "irobot":       "UFE",    # iRobot（3 位早期代码）
}

BRAND_NAMES: dict[str, str] = {
    "石头":         "Roborock",    "roborock":     "Roborock",
    "云鲸":         "Narwal",      "narwal":       "Narwal",
    "追觅":         "Dreame",      "dreame":       "Dreame",
    "科沃斯":       "Ecovacs",     "ecovacs":      "Ecovacs",
    "卧安":         "SwitchBot",   "switchbot":    "SwitchBot",   "woan": "SwitchBot",
    "杉川":         "3irobotics",  "3irobotics":   "3irobotics",
    "安克":         "Eufy",        "eufy":         "Eufy",
    "小米":         "Xiaomi",      "xiaomi":       "Xiaomi",
    "必胜":         "Bissell",     "bissell":      "Bissell",
    "irobot":       "iRobot",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
FCCID_BASE   = "https://fccid.io"    # 文档列表解析（静态 HTML）
FCC_REPORT   = "https://fcc.report"  # PDF 实际下载（完整文件）


# ── 工具函数 ───────────────────────────────────────────────────────

def _slug(model: str) -> str:
    return re.sub(r"[\s\-]+", "", model)


def _detect_brand(model: str) -> tuple[str | None, str | None]:
    low = model.lower()
    for kw, code in BRAND_FCC_CODE.items():
        if kw in low:
            return code, BRAND_NAMES.get(kw)
    return None, None


def _global_name(model: str, brand: str | None) -> str | None:
    try:
        from core.model_aliases import cn_to_global, find_alias
        name = cn_to_global(model, brand)
        if name:
            return name
        hits = find_alias(model, brand, top_k=1)
        if hits and hits[0].score >= 0.5:
            return hits[0].global_model
    except Exception:
        pass
    return None


def _get(url: str, retries: int = 3, stream: bool = False) -> requests.Response:
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, stream=stream)
            r.raise_for_status()
            return r
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


# ── fccid.io 爬取 ─────────────────────────────────────────────────

def get_grantee_applications(grantee_code: str) -> list[dict]:
    """
    从 fccid.io/{grantee_code} 解析申请列表。
    fccid.io 产品页静态 HTML 包含完整文档链接，无需 JS 渲染。
    """
    url  = f"{FCCID_BASE}/{grantee_code}"
    html = _get(url).text

    # fccid.io 格式：href=https://fccid.io/{grantee_code}-XXXXX 或 /{grantee_code}-XXXXX
    pattern = rf'href=(?:https://fccid\.io)?/({re.escape(grantee_code)}-[\w]+)'
    ids = list(dict.fromkeys(re.findall(pattern, html, re.I)))
    return [{"fcc_id": fid, "action_date": ""} for fid in ids]


def get_fcc_documents(fcc_id: str) -> list[dict]:
    """
    从 fcc.report/FCC-ID/{fcc_id} 解析文档列表（静态 HTML，PDF 直链可用）。
    """
    url  = f"{FCC_REPORT}/FCC-ID/{fcc_id}"
    html = _get(url).text

    pattern = rf'href=\"(/FCC-ID/{re.escape(fcc_id)}/(\d+))\"[^>]*>(.*?)</a>'
    matches = re.findall(pattern, html, re.S)

    docs: list[dict] = []
    for href, doc_id, label in matches:
        title = re.sub(r"<[^>]+>", "", label).strip()
        if not title:
            continue
        docs.append({
            "doc_id":   doc_id,
            "title":    title,
            "pdf_url":  f"{FCC_REPORT}{href}.pdf",
            "page_url": f"{FCC_REPORT}{href}",
        })
    return docs


def match_fcc_id(applications: list[dict], search_name: str, model: str,
                 prefer_with_photos: bool = True) -> str:
    """
    从申请列表匹配最相近的 FCC ID。
    prefer_with_photos=True 时：优先选有 Internal Photos 的申请；
    若所有申请都没有内部照片（confidential），回退到最新申请。
    """
    if not applications:
        raise ValueError("申请列表为空")

    slug_s = _slug(search_name).upper()
    slug_m = _slug(model).upper()

    def name_score(fcc_id: str) -> int:
        code = fcc_id.upper().split("-", 1)[-1]
        s = 0
        for i in range(min(5, len(code))):
            prefix = code[:i + 1]
            if prefix in slug_s or prefix in slug_m:
                s += i + 1
        return s

    if prefer_with_photos:
        print("  → 扫描各申请文档列表，优先选有 Internal Photos 的…")
        candidates_with_photos = []
        for app in applications[:20]:  # 最多检查 20 条（避免太慢）
            try:
                docs = get_fcc_documents(app["fcc_id"])
                titles = " ".join(d["title"].lower() for d in docs)
                if "internal" in titles and "photo" in titles:
                    candidates_with_photos.append(app)
            except Exception:
                pass

        if candidates_with_photos:
            print(f"  ✓ 找到 {len(candidates_with_photos)} 条含内部照片的申请")
            best = max(candidates_with_photos, key=lambda a: name_score(a["fcc_id"]))
            return best["fcc_id"]
        print("  ⚠ 所有申请均无公开内部照片（confidential），使用最新申请")

    return applications[0]["fcc_id"]


# ── PDF 下载 → 本地 PNG ───────────────────────────────────────────

def download_pdf(pdf_url: str, out_dir: Path, doc_label: str) -> Path:
    """
    下载 PDF 保存本地，返回 PDF 路径。若已存在则跳过下载（缓存）。
    """
    safe_label = re.sub(r"[^\w\-]", "_", doc_label)[:40]
    pdf_dir    = out_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    out_path   = pdf_dir / f"{safe_label}.pdf"

    if out_path.exists():
        print(f"  ✓ 使用缓存 PDF：{out_path.name} ({out_path.stat().st_size//1024}KB)")
        return out_path

    print(f"  → 下载 PDF: {pdf_url}")
    r = _get(pdf_url)
    if b"%PDF" not in r.content[:10]:
        raise ValueError(f"响应不是 PDF（前10字节: {r.content[:10]}）")
    out_path.write_bytes(r.content)
    print(f"  ✓ 已保存：{out_path.name} ({len(r.content)//1024}KB)")
    return out_path


def pdf_to_images_b64(pdf_path: Path, max_pages: int = 8) -> list[str]:
    """PDF → base64 PNG 列表（OCR 时临时转换，不持久化）。需要 pymupdf。"""
    try:
        import fitz
    except ImportError:
        raise ImportError("请安装 pymupdf: pip install pymupdf")

    import base64
    doc = fitz.open(str(pdf_path))
    images = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        images.append(base64.b64encode(pix.tobytes("png")).decode())
    doc.close()
    return images


# ── 视觉 OCR 分析 ─────────────────────────────────────────────────

import os as _os

_AIHUBMIX_KEY   = _os.environ.get("AIHUBMIX_API_KEY", "")
_AIHUBMIX_BASE  = _os.environ.get("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1")
_AIHUBMIX_MODEL = _os.environ.get("AIHUBMIX_MODEL", "gpt-4o")

_VISION_SYSTEM = (
    "你是扫地机器人硬件逆向专家，擅长从 PCB 照片识别芯片丝印。"
    "只输出 JSON 数组，不要任何 markdown 或解释性文字。"
)

_VISION_PROMPT = """\
这是扫地机器人 **{model}** 的 FCC 文档（{doc_type}）第 {page} 页。

请识别图片中所有可见的芯片/模组丝印：
SoC/CPU · Wi-Fi/BT 模组 · PMIC · MCU · 激光雷达主控 · 其他芯片

输出 JSON 数组（直接输出，不要代码块）：
[{{"bom_bucket":"compute_electronics","section":"主板","name":"SoC","model":"RK3588S","type":"主控芯片","spec":"","manufacturer":"瑞芯微","unit_price":0,"qty":1,"confidence":"fcc"}}]

无法识别时输出 []\
"""


def _img_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def analyze_pdf(pdf_path: Path, model: str, doc_type: str, max_pages: int = 8) -> list[dict]:
    """将 PDF 临时转换为图片并逐页 OCR，返回识别到的零件列表。"""
    images_b64 = pdf_to_images_b64(pdf_path, max_pages=max_pages)
    all_parts: list[dict] = []
    for i, img_b64 in enumerate(images_b64):
        prompt = _VISION_PROMPT.format(model=model, doc_type=doc_type, page=i + 1)
        try:
            if _AIHUBMIX_KEY:
                parts = _ocr_openai(img_b64, prompt)
            else:
                parts = _ocr_anthropic(img_b64, prompt)
            print(f"    第 {i+1} 页：识别到 {len(parts)} 个零件")
            all_parts.extend(parts)
        except Exception as e:
            print(f"    第 {i+1} 页 OCR 失败: {e}")
    return all_parts


def _ocr_openai(img_b64: str, prompt: str) -> list[dict]:
    import openai
    client = openai.OpenAI(api_key=_AIHUBMIX_KEY, base_url=_AIHUBMIX_BASE)
    resp = client.chat.completions.create(
        model=_AIHUBMIX_MODEL,
        max_completion_tokens=2048,
        messages=[
            {"role": "system", "content": _VISION_SYSTEM},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"}},
                {"type": "text",      "text": prompt},
            ]},
        ],
    )
    return _parse_parts(resp.choices[0].message.content or "")


def _ocr_anthropic(img_b64: str, prompt: str) -> list[dict]:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_VISION_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "image",  "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
            {"type": "text",   "text": prompt},
        ]}],
    )
    return _parse_parts(resp.content[0].text)


def _parse_parts(text: str) -> list[dict]:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return []


# ── 主采集函数 ────────────────────────────────────────────────────

def fetch_fcc(model: str, fcc_id_override: str | None = None,
              download_only: bool = False) -> dict:
    grantee_code, brand = _detect_brand(model)
    if not grantee_code and not fcc_id_override:
        raise ValueError("无法识别品牌 FCC code，请通过 --fcc-id 手动指定")

    global_name = _global_name(model, brand) if brand else None
    search_name = global_name or model

    slug    = _slug(model)
    out_dir = FCC_DIR / slug

    # ── 1. 确定 FCC ID ─────────────────────────────────────────────
    if fcc_id_override:
        fcc_id = fcc_id_override
        print(f"  → 使用指定 FCC ID: {fcc_id}")
    else:
        print(f"  → 搜索 fccid.io/{grantee_code} 申请列表…")
        apps = get_grantee_applications(grantee_code)
        if not apps:
            raise ValueError(f"未找到 {grantee_code} 的任何 FCC 申请")
        print(f"  ✓ 找到 {len(apps)} 条申请")
        fcc_id = match_fcc_id(apps, search_name, model)
        print(f"  → 匹配 FCC ID: {fcc_id}（搜索词: {search_name}）")

    # ── 2. 获取文档列表 ────────────────────────────────────────────
    print(f"  → 解析 {fcc_id} 文档列表…")
    docs = get_fcc_documents(fcc_id)
    print(f"  ✓ 找到 {len(docs)} 份文档：{[d['title'] for d in docs]}")

    # ── 3. 筛选目标文档 ────────────────────────────────────────────
    priority = ["Internal Photos", "Parts List", "Block Diagram"]
    target_docs: list[dict] = []
    for kw in priority:
        target_docs.extend(d for d in docs if kw.lower() in d["title"].lower())
    if not target_docs:
        target_docs = docs[:3]

    # ── 4. 下载 PDF → 本地存档 ───────────────────────────────────
    all_parts: list[dict] = []
    sources_used: list[str] = []
    downloaded_pdfs: list[tuple[dict, Path]] = []

    for doc in target_docs[:3]:
        print(f"\n  ── {doc['title']} ──")
        try:
            pdf_path = download_pdf(doc["pdf_url"], out_dir, doc["title"])
            downloaded_pdfs.append((doc, pdf_path))
            sources_used.append(doc["title"])
        except Exception as e:
            print(f"  ⚠ {doc['title']} 下载失败: {e}")

    pdfs_dir = out_dir / "pdfs"
    print(f"\n  ✓ 下载完成，共 {len(downloaded_pdfs)} 份 PDF → {pdfs_dir}")

    if download_only:
        return {
            "fcc_id":       fcc_id,
            "grantee_code": grantee_code or "",
            "search_name":  search_name,
            "sources_used": sources_used,
            "pdfs_dir":     str(pdfs_dir),
            "parts":        [],
            "model":        model,
            "fetched_at":   date.today().isoformat(),
        }

    # ── 5. OCR 分析（临时转换 PDF → 图片，不持久化）─────────────
    for doc, pdf_path in downloaded_pdfs:
        print(f"\n  → OCR: {doc['title']}…")
        try:
            parts = analyze_pdf(pdf_path, model, doc["title"])
            print(f"  ✓ 识别到 {len(parts)} 个零件")
            all_parts.extend(parts)
        except ImportError:
            raise
        except Exception as e:
            print(f"  ⚠ OCR 失败: {e}")

    # 去重（name + model 组合）
    seen: set[str] = set()
    unique_parts: list[dict] = []
    for p in all_parts:
        key = f"{p.get('name','')}/{p.get('model','')}"
        if key not in seen:
            seen.add(key)
            unique_parts.append(p)

    return {
        "fcc_id":       fcc_id,
        "grantee_code": grantee_code or "",
        "search_name":  search_name,
        "sources_used": sources_used,
        "pdfs_dir":     str(pdfs_dir),
        "parts":        unique_parts,
        "model":        model,
        "fetched_at":   date.today().isoformat(),
    }


def save_fcc(model: str, fcc_id: str, data: dict) -> Path:
    slug    = _slug(model)
    out_dir = FCC_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    fcc_file = out_dir / f"{fcc_id}.json"
    fcc_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return fcc_file


# CSV schema 对齐 scripts/gen_teardown.py::CSV_FIELDS
# gen_teardown.py 会扫 data/teardowns/fcc/{slug}/*_fcc_*.csv 作为上游喂入 Stage 1。
_TEARDOWN_CSV_FIELDS = [
    "bom_bucket", "section", "name", "model", "type",
    "spec", "manufacturer", "qty", "source_url", "updated_at", "product_source",
    "_unit_price", "_line_cost", "_price_src",
]


def write_fcc_csv(model: str, fcc_id: str, data: dict) -> Path | None:
    """把 FCC OCR 产出的 parts 写成上游 CSV，schema 对齐拆机 CSV。

    parts 为空时不写（OCR 未接入或识别失败），返回 None。
    """
    parts = data.get("parts") or []
    if not parts:
        return None

    slug     = _slug(model)
    out_dir  = FCC_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    fetched  = data.get("fetched_at") or date.today().isoformat()
    date_tag = fetched.replace("-", "")
    csv_path = out_dir / f"{slug}_fcc_{date_tag}.csv"
    application_url = f"https://fccid.io/{fcc_id}"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_TEARDOWN_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for p in parts:
            w.writerow({
                "bom_bucket":     p.get("bom_bucket") or "",
                "section":        p.get("section") or "",
                "name":           p.get("name") or "",
                "model":          p.get("model") or "",
                "type":           p.get("type") or "",
                "spec":           p.get("spec") or "",
                "manufacturer":   p.get("manufacturer") or "",
                "qty":            p.get("qty") or 1,
                "source_url":     application_url,
                "updated_at":     fetched,
                "product_source": "fcc",
                "_unit_price":    p.get("unit_price") or "",
                "_line_cost":     "",  # Stage 4 填
                "_price_src":     "",  # Stage 4 填
            })
    return csv_path


# ── fcc_find：查找 FCC ID + 列出文档链接 ─────────────────────────

def cmd_find(model: str, fcc_id_override: str | None, force: bool) -> None:
    """
    Step 1：在 fccid.io 查找匹配的 FCC ID，列出文档链接。
    结果写入 data/teardowns/fcc/{slug}/links.json，供人工确认后进行 OCR。
    """
    slug    = _slug(model)
    out_dir = FCC_DIR / slug
    links_file = out_dir / "links.json"

    if links_file.exists() and not force:
        cached = json.loads(links_file.read_text(encoding="utf-8"))
        fcc_id = cached.get("fcc_id", "")
        docs   = cached.get("docs", [])
        print(f"✓ 已有缓存（使用 --force 强制重新查找）：{links_file}")
        print(f"  FCC ID:  {fcc_id}")
        print(f"  fccid.io 页面:  https://fccid.io/{fcc_id}")
        print(f"  fcc.report 页面: https://fcc.report/FCC-ID/{fcc_id}")
        print(f"\n  文档列表（{len(docs)} 份）：")
        for d in docs:
            print(f"  [{d['doc_id']}] {d['title']}")
            print(f"      页面: {d['page_url']}")
            print(f"      PDF:  {d['pdf_url']}")
        print(f"\n  下一步: python scripts/fetch_fcc.py ocr \"{model}\"")
        return

    grantee_code, brand = _detect_brand(model)
    if not grantee_code and not fcc_id_override:
        print(f"✗ 无法识别品牌 FCC code，请通过 --fcc-id 手动指定", file=sys.stderr)
        sys.exit(1)

    global_name = _global_name(model, brand) if brand else None
    search_name = global_name or model

    if fcc_id_override:
        fcc_id = fcc_id_override
        print(f"  → 使用指定 FCC ID: {fcc_id}")
    else:
        print(f"  → 搜索 fccid.io/{grantee_code} 申请列表…")
        try:
            apps = get_grantee_applications(grantee_code)
        except Exception as e:
            print(f"✗ 查找失败：{e}", file=sys.stderr)
            sys.exit(1)
        if not apps:
            print(f"✗ 未找到 {grantee_code} 的任何 FCC 申请", file=sys.stderr)
            sys.exit(1)
        print(f"  ✓ 找到 {len(apps)} 条申请")
        fcc_id = match_fcc_id(apps, search_name, model)
        print(f"  → 匹配 FCC ID: {fcc_id}（搜索词: {search_name}）")

    print(f"  → 解析 {fcc_id} 文档列表…")
    try:
        docs = get_fcc_documents(fcc_id)
    except Exception as e:
        print(f"✗ 文档列表获取失败：{e}", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    links_data = {
        "fcc_id":       fcc_id,
        "grantee_code": grantee_code or "",
        "search_name":  search_name,
        "model":        model,
        "found_at":     date.today().isoformat(),
        "docs":         docs,
    }
    links_file.write_text(json.dumps(links_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ 已保存链接索引：{links_file}")
    print(f"  FCC ID:          {fcc_id}")
    print(f"  fccid.io 页面:   https://fccid.io/{fcc_id}")
    print(f"  fcc.report 页面: https://fcc.report/FCC-ID/{fcc_id}")
    print(f"\n  文档列表（{len(docs)} 份）：")

    priority = {"internal photos", "parts list", "block diagram"}
    for d in docs:
        tag = " ★" if any(kw in d["title"].lower() for kw in priority) else ""
        print(f"  [{d['doc_id']}] {d['title']}{tag}")
        print(f"      页面: {d['page_url']}")
        print(f"      PDF:  {d['pdf_url']}")

    print(f"\n  ★ = 推荐 OCR 目标（Internal Photos / Parts List / Block Diagram）")
    print(f"  下一步: python scripts/fetch_fcc.py ocr \"{model}\"")


# ── fcc_ocr：下载 PDF + 视觉 OCR ─────────────────────────────────

def cmd_ocr(model: str, fcc_id_override: str | None, force: bool) -> None:
    """
    Step 2：从 links.json 读取文档列表，下载目标 PDF，运行 OCR，输出 CSV。
    若 links.json 不存在则先自动执行 find 步骤。
    """
    slug    = _slug(model)
    out_dir = FCC_DIR / slug
    links_file = out_dir / "links.json"
    latest     = out_dir / "latest.json"

    if latest.exists() and not force:
        data  = json.loads(latest.read_text(encoding="utf-8"))
        parts = data.get("parts", [])
        print(f"✓ 已有 OCR 结果（使用 --force 强制重跑）：{latest}")
        print(f"  FCC ID: {data.get('fcc_id')}，识别到 {len(parts)} 个零件")
        for p in parts:
            print(f"  • [{p.get('bom_bucket')}] {p.get('name')} {p.get('model')} ({p.get('manufacturer')})")
        csv_path = write_fcc_csv(model, data.get("fcc_id", slug), data)
        if csv_path:
            print(f"  上游 CSV：{csv_path}")
        return

    # 若没有 links.json，先自动 find
    if not links_file.exists():
        print(f"  ⚠ 未找到链接索引，先执行 find 步骤…")
        cmd_find(model, fcc_id_override, force=False)
        if not links_file.exists():
            sys.exit(1)

    links_data = json.loads(links_file.read_text(encoding="utf-8"))
    fcc_id     = fcc_id_override or links_data.get("fcc_id", slug)
    all_docs   = links_data.get("docs", [])

    # 筛选目标文档
    priority = ["Internal Photos", "Parts List", "Block Diagram"]
    target_docs: list[dict] = []
    for kw in priority:
        target_docs.extend(d for d in all_docs if kw.lower() in d["title"].lower())
    if not target_docs:
        target_docs = all_docs[:3]

    print(f"  → OCR 目标：{[d['title'] for d in target_docs[:3]]}")

    all_parts: list[dict] = []
    sources_used: list[str] = []
    downloaded_pdfs: list[tuple[dict, Path]] = []

    for doc in target_docs[:3]:
        print(f"\n  ── {doc['title']} ──")
        try:
            pdf_path = download_pdf(doc["pdf_url"], out_dir, doc["title"])
            downloaded_pdfs.append((doc, pdf_path))
            sources_used.append(doc["title"])
        except Exception as e:
            print(f"  ⚠ {doc['title']} 下载失败: {e}")

    for doc, pdf_path in downloaded_pdfs:
        print(f"\n  → OCR: {doc['title']}…")
        try:
            parts = analyze_pdf(pdf_path, model, doc["title"])
            print(f"  ✓ 识别到 {len(parts)} 个零件")
            all_parts.extend(parts)
        except ImportError as e:
            print(f"  ✗ 缺少依赖: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"  ⚠ OCR 失败: {e}")

    seen: set[str] = set()
    unique_parts: list[dict] = []
    for p in all_parts:
        key = f"{p.get('name','')}/{p.get('model','')}"
        if key not in seen:
            seen.add(key)
            unique_parts.append(p)

    grantee_code = links_data.get("grantee_code", "")
    search_name  = links_data.get("search_name", model)
    data = {
        "fcc_id":       fcc_id,
        "grantee_code": grantee_code,
        "search_name":  search_name,
        "sources_used": sources_used,
        "pdfs_dir":     str(out_dir / "pdfs"),
        "parts":        unique_parts,
        "model":        model,
        "fetched_at":   date.today().isoformat(),
    }
    saved = save_fcc(model, fcc_id, data)
    pdfs  = list((out_dir / "pdfs").glob("*.pdf")) if (out_dir / "pdfs").exists() else []

    print(f"\n✓ 已保存：{saved}")
    print(f"  本地 PDF：{len(pdfs)} 份 → {out_dir / 'pdfs'}")
    print(f"  识别零件：{len(unique_parts)} 个")
    for p in unique_parts:
        print(f"  • [{p.get('bom_bucket')}] {p.get('name')} {p.get('model')} ({p.get('manufacturer')})")
    csv_path = write_fcc_csv(model, fcc_id, data)
    if csv_path:
        print(f"  上游 CSV：{csv_path}（gen_teardown.py 将作为 Stage 1 上游）")


# ── CLI ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FCC 采集工具：find（查链接）/ ocr（OCR识别）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # Step 1：查找 FCC 文档链接（不下载）
  python scripts/fetch_fcc.py find "石头G30S Pro"
  python scripts/fetch_fcc.py find "科沃斯X8 Pro" --fcc-id 2A6HE-DEX8PRO

  # Step 2：下载 PDF 并 OCR 识别
  python scripts/fetch_fcc.py ocr "石头G30S Pro"
  python scripts/fetch_fcc.py ocr "石头G30S Pro" --force

  # 兼容旧用法（等价于 find + ocr）
  python scripts/fetch_fcc.py "石头G30S Pro"
        """,
    )
    subparsers = parser.add_subparsers(dest="cmd")

    # --- find ---
    p_find = subparsers.add_parser("find", help="查找 FCC ID 并列出文档链接（不下载）")
    p_find.add_argument("model",    help="机型名称，如 '石头G30S Pro'")
    p_find.add_argument("--fcc-id", help="直接指定 FCC ID（跳过品牌列表搜索）")
    p_find.add_argument("--force",  action="store_true", help="忽略缓存重新查找")

    # --- ocr ---
    p_ocr = subparsers.add_parser("ocr", help="下载 PDF 并运行视觉 OCR 识别零件")
    p_ocr.add_argument("model",    help="机型名称，如 '石头G30S Pro'")
    p_ocr.add_argument("--fcc-id", help="直接指定 FCC ID（跳过 links.json）")
    p_ocr.add_argument("--force",  action="store_true", help="忽略缓存重新 OCR")

    # --- 兼容旧用法：直接传 model（无子命令）---
    parser.add_argument("model_compat", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("--fcc-id",       help=argparse.SUPPRESS)
    parser.add_argument("--force",        action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--download-only",action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.cmd == "find":
        cmd_find(args.model, args.fcc_id, args.force)
    elif args.cmd == "ocr":
        cmd_ocr(args.model, args.fcc_id, args.force)
    elif args.model_compat:
        # 旧用法兼容：先 find 再 ocr
        model = args.model_compat
        fcc_id = args.fcc_id
        if args.download_only:
            cmd_find(model, fcc_id, args.force)
        else:
            cmd_find(model, fcc_id, args.force)
            cmd_ocr(model, fcc_id, args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
