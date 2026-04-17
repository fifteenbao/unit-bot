"""
从产品数据库.xlsx 批量导入产品到 products_db.json

用法：
    python scripts/import_products.py /path/to/产品数据库.xlsx
    python scripts/import_products.py  # 默认找 data/ 目录
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import upsert_product, update_completeness


# ── 辅助函数 ──────────────────────────────────────────────────────

def _bool(val) -> bool | None:
    if val is None:
        return None
    return str(val).strip() == "是"


def _int_from_str(val, pattern: str) -> int | None:
    """从字符串里提取第一个整数，例如 '22000Pa' → 22000"""
    if val is None:
        return None
    m = re.search(pattern, str(val))
    return int(m.group(1)) if m else None


def _slug(brand: str, name: str) -> str:
    """生成唯一 key，例如 Roborock_G30Space"""
    clean = re.sub(r"[^\w\u4e00-\u9fff]", "", name)
    return f"{brand}_{clean}"[:64]


def _parse_row(headers: list, row: tuple) -> dict | None:
    d = dict(zip(headers, row))

    name = d.get("产品名称")
    brand = d.get("厂商名称")
    if not name or not brand:
        return None

    # 续航：'150分钟' → 150
    life = _int_from_str(d.get("续航"), r"(\d+)")

    # 越障高度：'越障高度可达 4cm' → 4
    obs = _int_from_str(d.get("越障高度"), r"(\d+(?:\.\d+)?)")

    # 吸力：'22000Pa' → 22000
    suction = _int_from_str(d.get("吸力"), r"(\d+)")

    # 电池容量：'6400mAh' → 6400
    battery_mah = _int_from_str(d.get("电池容量"), r"(\d+)")

    # 发布日期
    release = d.get("发布日期")
    release_str = None
    if isinstance(release, datetime):
        release_str = release.strftime("%Y-%m")
    elif release:
        release_str = str(release)[:7]

    # 商品链接（去掉 ==HYPERLINK 公式壳）
    url_raw = str(d.get("商品链接") or "")
    url_m = re.search(r'https?://[^\s"]+', url_raw)
    url = url_m.group(0).rstrip('"') if url_m else None

    specs = {
        "suction_power_pa":      suction,
        "battery_capacity_mah":  battery_mah,
        "battery_life_min":      life,
        "obstacle_height_cm":    obs,
        "navigation":            d.get("导航方式"),
        "mop_lift":              _bool(d.get("拖布抬升")),
        "self_cleaning":         _bool(d.get("是否自清洁")),
        "hot_air_dry":           _bool(d.get("自动烘干")),
        "auto_empty":            _bool(d.get("自动集尘")),
        "auto_wash":             _bool(d.get("自动清洗拖布")),
    }
    # 去掉全 None 的 specs
    specs = {k: v for k, v in specs.items() if v is not None}

    features = {
        "自动上下水":       _bool(d.get("自动上下水")),
        "自动添加清洁液":   _bool(d.get("自动添加清洁液")),
        "自动补水":         _bool(d.get("自动补水")),
        "底盘升降":         _bool(d.get("底盘升降")),
        "热水擦地":         _bool(d.get("热水擦地")),
        "热风烘干":         _bool(d.get("热风烘干")),
        "边角清洁":         _bool(d.get("边角清洁")),
        "毛发防缠":         _bool(d.get("毛发防缠")),
        "地毯加压清扫":     _bool(d.get("地毯加压清扫")),
        "智能避障":         _bool(d.get("智能避障")),
        "物体识别":         _bool(d.get("物体识别")),
        "语音交互":         _bool(d.get("语音交互")),
    }
    features = {k: v for k, v in features.items() if v is not None}

    return {
        "key": _slug(brand, name),
        "data": {
            "brand":            brand,
            "model_name":       name,
            "retail_price_cny": d.get("价格"),
            "release_date":     release_str,
            "market_segment":   None,
            "product_page_url": url,
            "data_sources": {
                "web_research": [url] if url else [],
                "completeness": {},
            },
            "specs":   specs,
            "features": features,
            "notes":   str(d.get("卖点摘要") or ""),
        },
    }


# ── 主流程 ────────────────────────────────────────────────────────

def import_from_xlsx(xlsx_path: Path) -> int:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    headers = [cell.value for cell in ws[1]]

    imported = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        parsed = _parse_row(headers, row)
        if not parsed:
            continue
        key = parsed["key"]
        upsert_product(key, parsed["data"])
        update_completeness(key)
        imported += 1
        print(f"  ✓ {key}")

    wb.close()
    return imported


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        data_dir = Path(__file__).parent.parent / "data"
        candidates = [f for f in data_dir.glob("*.xlsx") if "产品" in f.name]
        path = candidates[0] if candidates else None

    if not path or not path.exists():
        print("未找到产品数据库 xlsx，请传入路径：python scripts/import_products.py /path/to/产品数据库.xlsx")
        sys.exit(1)

    print(f"导入来源：{path}")
    count = import_from_xlsx(path)
    print(f"\n完成：共导入 {count} 条产品")
