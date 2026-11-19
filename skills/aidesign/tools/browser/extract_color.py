"""Роли цвета для extract.py: основной, акцент, фон, поверхность, текст, нейтральные, состояния.

По мотивам dembrandt (MIT, © 2025 thevangelist / © 2026 Dembrandt): веса контекста
(logo, brand, primary, cta, hero, button…), заливка кнопок как главный признак основного
цвета, отсев «структурного шума», уверенность с порогом по числу употреблений.
Изменено: свой код на Python, роли под наши токены, фон и текст — с body, состояния кнопок.
Цвета приходят из браузера уже приведёнными к #rrggbb или #rrggbbaa.
"""

import math
import re
from collections import Counter

CONTEXT = {"logo": 5, "brand": 5, "primary": 4, "cta": 4, "hero": 3, "button": 3, "btn": 3,
           "card": 2, "section": 2, "feature": 2, "panel": 2, "input": 2, "badge": 2, "chip": 2,
           "footer": 2, "link": 2, "header": 2, "nav": 1}
STATUS = re.compile(r"\b(error|danger|destructive|invalid|warning|success|alert|notice|sale|discount|toast|"
                    r"notification)\b")
ROLE_QUALIFIED = re.compile(r"(foreground|fg|text|label|border|outline|ring|icon|muted|hover|active|disabled|bg|"
                            r"background|surface)[-_ ]?primary|primary[-_ ]?(foreground|fg|text|label|border|outline|"
                            r"icon|hover|active|disabled|bg|background|surface)")
TOKEN_PRIMARY = re.compile(r"(?:^--|-)(?:primary|brand)(?:-(?:color|colou?r|base|default|main|\d{2,3}))?$")
TOKEN_SLOT = re.compile(r"(?:^--|-)(?:bg|background|surface|text|fg|foreground|border|outline|ring|icon|label|"
                        r"disabled|hover|active|muted|subtle)(?:-|$)")      # место на поверхности, не сам бренд
BUTTONISH = re.compile(r"button|btn|cta")
NEUTRAL_CTA = {"#000000", "#ffffff", "#efefef"}


# ── математика цвета ────────────────────────────────────────────────────────

def rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def alpha(h):
    h = h.lstrip("#")
    return int(h[6:8], 16) / 255 if len(h) == 8 else 1.0


def sat(h):
    r, g, b = rgb(h)
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx


def lum(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def hue(h):
    r, g, b = (x / 255 for x in rgb(h))
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0
    d = mx - mn
    if mx == r:
        x = ((g - b) / d) % 6
    elif mx == g:
        x = (b - r) / d + 2
    else:
        x = (r - g) / d + 4
    return x * 60


def hue_gap(a, b):
    d = abs(hue(a) - hue(b))
    return min(d, 360 - d)


def oklch(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb(h))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.hypot(A, B)
    H = math.degrees(math.atan2(B, A)) % 360 if C > 0.002 else 0
    return "oklch(%.1f%% %.3f %.1f)" % (L * 100, C, H)


def best_on(h, light="#ffffff", dark="#000000"):
    return light if contrast(h, light) >= contrast(h, dark) else dark


# ── сбор и роли ─────────────────────────────────────────────────────────────

def _blank():
    return {"count": 0, "score": 0, "bg": 0, "color": 0, "border": 0, "area": 0, "cta": 0, "ctaNeutral": 0,
            "status": 0, "primaryCtx": 0, "logo": 0, "on": Counter(), "token": None}


def _stats(raw):
    m = {}
    for e in raw.get("elements") or []:
        ctx = (e.get("ctx") or "").lower()
        score = max([w for k, w in CONTEXT.items() if k in ctx] + [3 if e.get("tag") == "button" else 0])
        status = bool(STATUS.search(ctx))
        buttonish = e.get("tag") == "button" or bool(BUTTONISH.search(ctx))
        if e.get("logo") and e.get("fill") and alpha(e["fill"]) >= 0.7:
            m.setdefault(e["fill"][:7].lower(), _blank())["logo"] += 1
        for kind in ("bg", "color", "border"):
            c = e.get(kind)
            if not c or (kind == "color" and not e.get("text")) or alpha(c) < (0.5 if kind == "color" else 0.1):
                continue
            h = c[:7].lower()
            d = m.setdefault(h, _blank())
            d["count"] += 1
            d["score"] += score
            d[kind] += 1
            d["status"] += status
            if kind == "bg":
                d["area"] += e.get("area") or 0
                if "primary" in ctx and not ROLE_QUALIFIED.search(ctx):
                    d["primaryCtx"] += 1
                if buttonish and alpha(c) >= 0.7:
                    if h in NEUTRAL_CTA or sat(h) < 0.12:          # серые кнопки — не бренд
                        d["ctaNeutral"] += 1
                    else:
                        d["cta"] += 1
                        d["score"] += 25
                    if e.get("color"):
                        d["on"][e["color"][:7].lower()] += 1
    for v in raw.get("vars") or []:
        if v.get("hex") and v["hex"][:7].lower() in m:
            m[v["hex"][:7].lower()]["token"] = v.get("name")
    return m


def _confidence(d):
    if d["token"]:
        c = "high" if d["score"] > 5 else "medium"
    else:
        c = "high" if d["score"] > 20 else "medium" if d["score"] > 5 else "low"
    if c == "high" and d["count"] < 3:
        c = "medium" if d["count"] >= 2 else "low"
    if c == "medium" and d["count"] < 2:
        c = "low"
    return c


def _primary(m, skip, vars_):
    def pick(cands, key):
        cands = [x for x in cands if x[0] not in skip]
        return max(cands, key=key)[0] if cands else None
    items = list(m.items())
    found = pick([x for x in items if x[1]["cta"] >= 2], lambda x: (x[1]["cta"], x[1]["score"]))
    if found:
        return found, "заливка кнопок (%d)" % m[found]["cta"]
    found = pick([x for x in items if x[1]["primaryCtx"] and lum(x[0]) < 0.6 and sat(x[0]) > 0.15],
                 lambda x: x[1]["primaryCtx"])                  # светлая плашка с «primary» — не бренд
    if found:
        return found, "элемент с классом primary"
    for v in vars_:
        h = (v.get("hex") or "")[:7].lower()
        if h and TOKEN_PRIMARY.search(v.get("name", "")) and not TOKEN_SLOT.search(v["name"]) \
                and h not in skip and lum(h) < 0.6:
            return h, "токен %s" % v["name"]
    found = pick([x for x in items if x[1]["logo"] and sat(x[0]) > 0.3], lambda x: x[1]["logo"])
    if found:
        return found, "цвет логотипа"
    found = pick([x for x in items if x[1]["cta"] == 1], lambda x: x[1]["score"])
    if found:
        return found, "заливка кнопки"
    found = pick([x for x in items if sat(x[0]) > 0.3 and _confidence(x[1]) != "low"],
                 lambda x: (sat(x[0]), x[1]["score"]))
    if found:
        return found, "самый яркий из частых цветов"
    found = pick([x for x in items if x[1]["ctaNeutral"] >= 2], lambda x: x[1]["ctaNeutral"])
    if found:
        return found, "общая заливка кнопок (сайт без яркого цвета)"
    return None, ""


def _state_color(raw, primary):
    hover = focus = None
    for b in raw.get("buttons") or []:
        base, hv, fc = b.get("base") or {}, b.get("hover") or {}, b.get("focus") or {}
        if primary and (base.get("bg") or "")[:7] == primary and hv.get("bg") and hv["bg"][:7] != primary:
            hover = hover or hv["bg"][:7]
        focus = focus or _focus_color(base, fc)
    for i in raw.get("inputs") or []:
        focus = focus or _focus_color(i.get("base") or {}, i.get("focus") or {})
    return hover, focus


def _focus_color(base, fc):
    if fc.get("outlineColor") and not str(fc.get("outline", "")).startswith("0px") \
            and "none" not in str(fc.get("outline", "")):
        return fc["outlineColor"][:7]
    return None


def color_roles(raw):
    """[{hex, oklch, role, confidence, count, on, why}] — только наблюдённое."""
    m = _stats(raw)
    body = raw.get("body") or {}
    bg, text = (body.get("bg") or "#ffffff")[:7].lower(), (body.get("color") or "#000000")[:7].lower()
    out = []

    def add(h, role, why, conf=None, on=None):
        d = m.get(h) or {"count": 0, "score": 0, "token": None}
        out.append({"hex": h, "oklch": oklch(h), "role": role, "confidence": conf or _confidence(d),
                    "count": d["count"], "on": on or best_on(h, *sorted((bg, text), key=lum, reverse=True)),
                    "why": why})
    add(bg, "background", "фон страницы (body)", "high", text)
    add(text, "text", "основной текст (body)", "high", bg)
    primary, why = _primary(m, {bg, text} if sat(bg) < 0.3 else {bg}, raw.get("vars") or [])
    taken = {bg, text}
    if primary:
        d = m.get(primary)
        on = d["on"].most_common(1)[0][0] if d and d["on"] else best_on(primary)
        add(primary, "primary", why, on=on)
        taken.add(primary)
    chroma = [(h, d) for h, d in m.items() if h not in taken and sat(h) > 0.3 and _confidence(d) != "low"
              and d["status"] < d["count"] and (not primary or sat(primary) < 0.15 or hue_gap(h, primary) >= 30)]
    if chroma:
        h = max(chroma, key=lambda x: (x[1]["score"], x[1]["count"]))[0]
        add(h, "accent", "яркий цвет другого оттенка")
        taken.add(h)
    for role, kind, why, extra in (
            ("surface", "bg", "заливка карточек и секций", lambda h, d: d["bg"] >= 2),
            ("text-muted", "color", "второстепенный текст", lambda h, d: d["color"] >= 2 and contrast(h, bg) >= 2),
            ("border", "border", "рамки и разделители", lambda h, d: True)):
        c = [(h, d) for h, d in m.items() if h not in taken and d[kind] and sat(h) <= 0.25 and extra(h, d)]
        if c:
            h = max(c, key=lambda x: (x[1]["area"] if kind == "bg" else x[1][kind]))[0]
            add(h, role, why)
            taken.add(h)
    hover, focus = _state_color(raw, primary)
    if hover:
        add(hover, "primary-hover", "кнопка под курсором", "medium", m[primary]["on"].most_common(1)[0][0]
            if primary in m and m[primary]["on"] else None)
    if focus:
        add(focus, "focus", "рамка фокуса", "medium")
    total = max(len(raw.get("elements") or []), 1)
    floor = max(3, total // 100)
    rest = [(h, d) for h, d in m.items() if h not in taken and (d["count"] >= floor or d["score"] >= 10)
            and not (d["count"] / total > 0.4 and sat(h) <= 0.2)]
    for h, d in sorted(rest, key=lambda x: -x[1]["count"])[:10]:
        role = "status" if d["status"] == d["count"] and sat(h) > 0.3 else "neutral" if sat(h) < 0.12 else "supporting"
        add(h, role, {"status": "сообщения и ошибки", "neutral": "нейтральный",
                      "supporting": "вспомогательный"}[role])
    return out
