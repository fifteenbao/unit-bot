from __future__ import annotations

import re
from typing import Iterable


_BRAND_ROWS: tuple[tuple[str, str, str], ...] = (
    ("石头", "2AN2O", "Roborock"),
    ("石头科技", "2AN2O", "Roborock"),
    ("roborock", "2AN2O", "Roborock"),
    ("roborocktechnology", "2AN2O", "Roborock"),
    ("云鲸", "2ARZZ", "Narwal"),
    ("narwal", "2ARZZ", "Narwal"),
    ("追觅", "2AX54", "Dreame"),
    ("追觅科技", "2AX54", "Dreame"),
    ("dreame", "2AX54", "Dreame"),
    ("dreametechnology", "2AX54", "Dreame"),
    ("科沃斯", "2A6HE", "Ecovacs"),
    ("科沃斯科技", "2A6HE", "Ecovacs"),
    ("ecovacs", "2A6HE", "Ecovacs"),
    ("ecovacsrobotics", "2A6HE", "Ecovacs"),
    ("卧安", "2AKXB", "SwitchBot"),
    ("卧安科技", "2AKXB", "SwitchBot"),
    ("switchbot", "2AKXB", "SwitchBot"),
    ("switchbottechnology", "2AKXB", "SwitchBot"),
    ("woan", "2AKXB", "SwitchBot"),
    ("杉川", "2A9W4", "3irobotics"),
    ("3irobotics", "2A9W4", "3irobotics"),
    ("shenzhen3irobotics", "2A9W4", "3irobotics"),
    ("安克", "2AOKB", "Eufy"),
    ("anker", "2AOKB", "Eufy"),
    ("ankerinnovations", "2AOKB", "Eufy"),
    ("eufy", "2AOKB", "Eufy"),
    ("小米", "2AFZZ", "Xiaomi"),
    ("xiaomi", "2AFZZ", "Xiaomi"),
    ("必胜", "2AS9L", "Bissell"),
    ("bissell", "2AS9L", "Bissell"),
    ("irobot", "UFE", "iRobot"),
)

BRAND_FCC_CODE: dict[str, str] = {alias: code for alias, code, _ in _BRAND_ROWS}
BRAND_NAMES: dict[str, str] = {alias: name for alias, _, name in _BRAND_ROWS}
BRAND_ALIAS_PRIORITY: tuple[str, ...] = tuple(
    sorted(BRAND_FCC_CODE.keys(), key=len, reverse=True)
)

_NORMALIZE_RE = re.compile(r"[\s/+\-·,，。、()（）_]+")
_FCC_SLUG_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("石头科技", "石头"),
    ("追觅科技", "追觅"),
    ("科沃斯科技", "科沃斯"),
    ("卧安科技", "卧安"),
    ("roborocktechnology", "roborock"),
    ("dreametechnology", "dreame"),
    ("ecovacsrobotics", "ecovacs"),
    ("switchbottechnology", "switchbot"),
    ("shenzhen3irobotics", "3irobotics"),
    ("ankerinnovations", "anker"),
)
_FCC_NOISE_WORDS: tuple[str, ...] = ("technology", "robotics", "shenzhen", "科技")


def normalize_brand_text(text: str) -> str:
    return _NORMALIZE_RE.sub("", (text or "")).lower()


def normalize_fcc_slug(text: str) -> str:
    slug = normalize_brand_text(text)
    for source, target in _FCC_SLUG_REPLACEMENTS:
        slug = slug.replace(normalize_brand_text(source), normalize_brand_text(target))
    for word in _FCC_NOISE_WORDS:
        slug = slug.replace(word, "")
    return slug


def detect_brand(model: str) -> tuple[str | None, str | None]:
    low = normalize_brand_text(model)
    for alias in BRAND_ALIAS_PRIORITY:
        if alias in low:
            return BRAND_FCC_CODE[alias], BRAND_NAMES[alias]
    return None, None


def brand_aliases_for(code: str | None = None) -> Iterable[str]:
    for alias, alias_code in BRAND_FCC_CODE.items():
        if code is None or alias_code == code:
            yield alias
