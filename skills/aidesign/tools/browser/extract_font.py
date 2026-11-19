"""Запасной шрифт для tokens.css extract.py: по категории шрифта, а не всегда sans-serif.

Категория — из каталога справочника `google-fonts.json` (рядом со скиллом или в копии
`.aidesign-work/справочник/`), затем по известным системным шрифтам и словам в имени.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif",
           "ui-serif", "ui-monospace", "ui-rounded", "math", "emoji"}
CATALOG = (os.path.join(HERE, "..", "..", "knowledge", "справочник", "google-fonts.json"),
           os.path.join(HERE, "..", "справочник", "google-fonts.json"))
BY_CATEGORY = {"Serif": "serif", "Monospace": "monospace"}
MONO_WORDS = ("mono", "code", "courier", "consolas", "menlo", "monaco", "fira code")
SERIF_WORDS = ("georgia", "times", "garamond", "baskerville", "bodoni", "didot", "playfair", "merriweather",
               "lora", "cormorant", "caslon", "palatino", "cambria", "spectral", "literata", "prata",
               "old standard", "tinos", "slab")
_catalog = None


def _families(stack):
    return [x.strip().strip("\"'") for x in (stack or "").split(",") if x.strip()]


def catalog():
    global _catalog
    if _catalog is None:
        _catalog = {}
        for path in CATALOG:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            _catalog = {x["family"].lower(): x.get("category", "") for x in data.get("families", [])}
            break
    return _catalog


def category(name):
    low = name.lower()
    known = catalog().get(low)
    if known is not None:
        return BY_CATEGORY.get(known, "sans-serif")
    if any(w in low for w in MONO_WORDS):
        return "monospace"
    if ("serif" in low and "sans" not in low) or any(w in low for w in SERIF_WORDS):
        return "serif"
    return None


def stack(value):
    """Стек шрифтов с запасным общим семейством его категории."""
    fams = _families(value)
    if any(f.lower() in GENERIC for f in fams):
        return value
    for f in fams:
        c = category(f)
        if c:
            return "%s, %s" % (value, c)
    return "%s, sans-serif" % value
