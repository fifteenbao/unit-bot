"""一次性脚本: 为 components_lib.csv 添加 price_tier 列 (默认 mass_production)。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.components_lib import LIB_FIELDS, LIB_FILE  # noqa: E402


def main():
    with LIB_FILE.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        old_fields = reader.fieldnames or []

    if "price_tier" in old_fields:
        print("已含 price_tier 字段, 跳过")
        return

    for r in rows:
        r.setdefault("price_tier", "mass_production")

    with LIB_FILE.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=LIB_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"已为 {len(rows)} 条记录补 price_tier=mass_production")


if __name__ == "__main__":
    main()
