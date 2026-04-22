"""
从 core/bom_8bucket_framework.json 导出人看/对账用的 CSV 到 data/lib/。

每次修改 JSON 模板后跑一次:
    python scripts/export_framework_csv.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.bucket_framework import load_framework  # noqa: E402

OUT_CSV = ROOT / "data" / "lib" / "bom_8bucket_framework.csv"


def main():
    fw = load_framework()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["桶序", "桶(中)", "桶(英)", "行业占比基准",
                    "子项", "典型规格/配置", "目标机型单价¥(待填)", "备注"])
        for _, b in sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"]):
            for i, item in enumerate(b["typical_items"]):
                w.writerow([
                    b["order"] if i == 0 else "",
                    b["name_cn"] if i == 0 else "",
                    b["name_en"] if i == 0 else "",
                    (f"{b['industry_pct_avg']}% "
                     f"({b['industry_pct_range'][0]}-{b['industry_pct_range'][1]}%)")
                    if i == 0 else "",
                    item["name"],
                    item.get("example_spec", ""),
                    "",
                    "",
                ])
            for note in b.get("boundary_notes", []):
                w.writerow(["", "", "", "", "— 边界说明 —", "", "", note])
        w.writerow([""] * 8)
        w.writerow(["合计", "", "", "100%", "整机 BOM", "", "", ""])
    print(f"✓ 已写 {OUT_CSV} ({OUT_CSV.stat().st_size} B)")


if __name__ == "__main__":
    main()
