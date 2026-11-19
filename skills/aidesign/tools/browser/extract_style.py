"""Разбор снятого браузером для extract.py: шрифты, шкала, отступы, формы, движение, брейкпоинты,
компоненты; затем extract.json, tokens.css нашего формата и report.md. Без браузера — тестируется
на готовом ответе `browser/extract.mjs`. Роли цвета — extract_color.py.
"""

import datetime as dt
import re
import urllib.parse
from collections import Counter

import extract_color as col
import extract_font

HEADINGS = {"h1", "h2", "h3"}
SNAP_KEYS = ("bg", "color", "border", "borderColor", "radius", "padding", "fs", "fw", "shadow",
             "outline", "outlineColor", "decoration")


def _num(v):
    try:
        return float(str(v).replace("px", ""))
    except ValueError:
        return None


def _fmt(x):
    return int(x) if float(x).is_integer() else x


def _family(stack):
    first = (stack or "").split(",")[0].strip().strip("\"'")
    return first or None


def typography(els, fonts):
    text = [e for e in els if e.get("text") and _num(e.get("fs"))]
    heads = Counter(_family(e["ff"]) for e in text if e["tag"] in HEADINGS or re.search(r"title|heading|display",
                                                                                           e.get("ctx", "")))
    body = Counter(_family(e["ff"]) for e in text if e["tag"] not in HEADINGS)
    stacks = {_family(e["ff"]): e["ff"] for e in text}
    loaded = set(fonts or [])
    fams = []
    for use, cnt in (("heading", heads), ("body", body)):
        cnt.pop(None, None)
        if cnt:
            name, n = cnt.most_common(1)[0]
            fams.append({"name": name, "stack": stacks[name], "use": use, "count": n, "loaded": name in loaded})
    sizes, tags = Counter(), {}
    for e in text:
        px = _fmt(round(_num(e["fs"]) * 2) / 2)
        sizes[px] += 1
        tags.setdefault(px, set()).add(e["tag"])
    scale = [{"px": px, "count": n, "tags": sorted(tags[px])} for px, n in sizes.items()
             if n >= 2 or tags[px] & HEADINGS]
    scale.sort(key=lambda s: -s["px"])
    weights = Counter(str(e.get("fw")) for e in text)
    lhs = Counter()
    for e in text:
        lh = _num(e.get("lh"))
        if lh:
            lhs[round(round(lh / _num(e["fs"]) * 20) / 20, 2)] += 1
    return {"families": fams, "scale": scale,
            "weights": [{"weight": w, "count": n} for w, n in weights.most_common()],
            "lineHeights": [{"ratio": r, "count": n} for r, n in lhs.most_common(6)]}


def spacing(els):
    c = Counter()
    for e in els:
        for v in (e.get("pad") or []) + (e.get("mar") or []) + (e.get("gap") or []):
            n = _num(v)
            if n and 0 < n <= 256:
                c[int(round(n))] += 1
    vals = sorted(px for px, n in c.most_common(12) if n >= 2)
    out = [{"px": px, "count": c[px]} for px in vals]
    total = sum(c[px] for px in vals) or 1
    base = next((b for b in (8, 4) if sum(c[px] for px in vals if px % b == 0) / total >= 0.7), None)
    return out, base


def counted(values, limit=8):
    return [{"value": v, "count": n} for v, n in Counter(values).most_common(limit)]


def radius(els):
    vals = []
    for e in els:
        r = str(e.get("radius") or "0px").split()[0]
        n = _num(r)
        if r.endswith("%"):
            vals.append(r)
        elif n and n > 0:
            vals.append("9999px" if n >= 999 else "%spx" % _fmt(round(n, 1)))
    out = counted(vals, 8)
    out.sort(key=lambda x: (x["value"].endswith("%"), _num(x["value"].rstrip("%")) or 0))
    return out


def motion(els):
    durs, eases = [], []
    for e in els:
        for d_key, t_key in (("td", "tt"), ("ad", "at")):
            ds = [x.strip() for x in str(e.get(d_key) or "0s").split(",")]
            ts = re.split(r",(?![^(]*\))", str(e.get(t_key) or "ease"))
            for i, d in enumerate(ds):
                ms = _num(d[:-2]) if d.endswith("ms") else (_num(d[:-1]) or 0) * 1000 if d.endswith("s") else None
                if ms:
                    durs.append("%dms" % round(ms))
                    eases.append(ts[min(i, len(ts) - 1)].strip())
    return {"durations": counted(durs, 6), "easings": counted(eases, 6)}


def breakpoints(media):
    c, kinds = Counter(), {}
    for m in media or []:
        for kind, n, unit in re.findall(r"(min|max)-width\s*:\s*([\d.]+)(px|em|rem)", m):
            px = int(round(float(n) * (16 if unit != "px" else 1)))
            if 240 <= px <= 3000:
                c[px] += 1
                kinds.setdefault(px, kind)
    return [{"px": px, "count": c[px], "kind": kinds[px]} for px in sorted(c)]


def _component(item, state_keys, key):
    base = {k: item["base"].get(k) for k in SNAP_KEYS if item["base"].get(k) not in (None, "")}
    states = {}
    for s in state_keys:
        snap = item.get(s) or {}
        diff = {k: snap.get(k) for k in SNAP_KEYS if snap.get(k) not in (None, "") and snap.get(k) != base.get(k)}
        if diff:
            states[s] = diff
    return dict(base, states=states), tuple(base.get(k) for k in key)


def components(raw):
    out = {}
    for name, states, key, limit in (("buttons", ("hover", "focus"), ("bg", "color", "radius", "border"), 6),
                                     ("inputs", ("focus",), ("bg", "border", "borderColor", "radius"), 4),
                                     ("links", ("hover",), ("color", "decoration"), 4)):
        seen, items = set(), []
        for item in raw.get(name) or []:
            if not item.get("base"):
                continue
            comp, sig = _component(item, states, key)
            if sig not in seen:
                seen.add(sig)
                items.append(comp)
        out[name] = items[:limit]
    return out


def analyze(raw, url, robots, mobile=False, dark_requested=None, at=None):
    els = raw.get("elements") or []
    space, base = spacing(els)
    shadows = counted([e["shadow"] for e in els if e.get("shadow") and e["shadow"] != "none"], 6)
    res = {"colors": col.color_roles(raw), "typography": typography(els, raw.get("fonts")),
           "spacing": space, "spacingBase": base, "radius": radius(els), "shadows": shadows,
           "motion": motion(els), "breakpoints": breakpoints(raw.get("media")), "components": components(raw),
           "dark": None}
    if raw.get("dark"):
        d = raw["dark"]
        res["dark"] = {"differs": (d.get("body") or {}) != (raw.get("body") or {}), "colors": col.color_roles(d)}
    roles = {c["role"] for c in res["colors"]}
    missing = [w for w, ok in (("основной цвет", "primary" in roles), ("акцент", "accent" in roles),
                               ("поверхность", "surface" in roles), ("тени", shadows),
                               ("скругления", res["radius"]), ("шкала отступов", space),
                               ("движение", res["motion"]["durations"]), ("брейкпоинты", res["breakpoints"]),
                               ("кнопки", res["components"]["buttons"]), ("поля ввода", res["components"]["inputs"]))
               if not ok]
    if (dark_requested or raw.get("dark")) and not (res["dark"] or {}).get("differs"):
        missing.append("тёмная тема")
    res["missing"] = missing
    res["source"] = {"url": url, "finalUrl": raw.get("finalUrl") or url,
                     "domain": urllib.parse.urlsplit(url).hostname, "at": at or dt.datetime.now().isoformat(
                         timespec="seconds"), "robots": robots, "consent": raw.get("consent"),
                     "browser": raw.get("browser"), "viewport": raw.get("viewport"), "mobile": bool(mobile)}
    return res


# ── tokens.css и report.md ──────────────────────────────────────────────────

ROLE_TOKEN = {"primary": "primary", "accent": "accent", "background": "bg", "surface": "surface",
              "text": "text", "text-muted": "text-muted", "border": "border", "primary-hover": "primary-hover",
              "focus": "focus"}


def _color_lines(colors):
    lines, n = [], Counter()
    for c in colors:
        name = ROLE_TOKEN.get(c["role"])
        if not name:
            n[c["role"]] += 1
            name = "%s-%d" % (c["role"], n[c["role"]])
        lines.append("  --color-%s: %s;" % (name, c["hex"]))
        if c["role"] == "primary":
            lines.append("  --color-on-primary: %s;" % c["on"])
    return lines


def own_site(r):
    return r["source"].get("robots") == "own-site"


def tokens_css(r):
    s = r["source"]
    if own_site(r):
        head = ("/* AI Design: снято с вашего сайта %s %s; не наблюдалось: %s.\n"
                "   Черновик для design-system/tokens.css: ваши цвета, шрифты и формы как есть. Адрес: %s */\n"
                % (s["domain"], s["at"][:10], ", ".join(r["missing"]) or "ничего", s["url"]))
    else:
        head = ("/* AI Design: снято с %s %s: принципы, не бренд; не наблюдалось: %s.\n"
                "   Черновик для design-system/tokens.css. Логотип, тексты и фирменные шрифты не переносятся:\n"
                "   шрифт бренда замените похожим свободным. Адрес: %s */\n"
                % (s["domain"], s["at"][:10], ", ".join(r["missing"]) or "ничего", s["url"]))
    lines = _color_lines(r["colors"])
    for f in r["typography"]["families"]:
        lines.append("  --font-%s: %s;" % (f["use"], extract_font.stack(f["stack"])))
    for i, x in enumerate(r["typography"]["scale"][:8], 1):
        lines.append("  --font-size-%d: %spx;" % (i, x["px"]))
    for i, x in enumerate(r["typography"]["weights"][:4], 1):
        lines.append("  --font-weight-%d: %s;" % (i, x["weight"]))
    for i, x in enumerate(r["typography"]["lineHeights"][:3], 1):
        lines.append("  --font-leading-%d: %s;" % (i, x["ratio"]))
    lines += ["  --space-%d: %dpx;" % (i, x["px"]) for i, x in enumerate(r["spacing"], 1)]
    for i, x in enumerate(r["radius"], 1):
        lines.append("  --radius-%s: %s;" % ("full" if x["value"] == "9999px" else i, x["value"]))
    lines += ["  --shadow-%d: %s;" % (i, x["value"]) for i, x in enumerate(r["shadows"][:4], 1)]
    lines += ["  --motion-duration-%d: %s;" % (i, x["value"]) for i, x in enumerate(r["motion"]["durations"][:4], 1)]
    lines += ["  --motion-ease-%d: %s;" % (i, x["value"]) for i, x in enumerate(r["motion"]["easings"][:3], 1)]
    css = head + ":root {\n" + "\n".join(lines) + "\n}\n"
    if r.get("dark") and r["dark"]["differs"]:
        css += "\n[data-theme=dark] {\n" + "\n".join(_color_lines(r["dark"]["colors"])) + "\n}\n"
    return css


WORDS = {"background": "фон", "text": "текст", "primary": "основной", "accent": "акцент", "surface": "поверхность",
         "text-muted": "второстепенный текст", "border": "рамки", "primary-hover": "основной под курсором",
         "focus": "фокус", "status": "сообщения", "neutral": "нейтральный", "supporting": "вспомогательный"}
CONF = {"high": "уверенно", "medium": "скорее да", "low": "под вопросом"}


def report_md(r):
    s, t = r["source"], r["typography"]
    out = ["# Стиль с вашего сайта %s" % s["domain"] if own_site(r) else "# Стиль с %s" % s["domain"], "",
           ("Снято %s с вашего сайта %s: ваши цвета, шрифты и формы — их можно брать как есть." if own_site(r) else
            "Снято %s с %s. Это **принципы, не бренд**: логотип, тексты и фирменные шрифты не переносим.")
           % (s["at"][:10], s["url"]), "",
           "robots.txt: %s. Окно cookies: %s." % (
               {"allowed": "разрешает", "no-file": "нет файла", "own-site": "не проверялся — сайт человека"}
               .get(s["robots"], s["robots"]),
               "закрыто кнопкой «%s»" % s["consent"]["text"] if s.get("consent") else "не встретилось"), "",
           "## Цвета", "", "| роль | цвет | уверенность | почему |", "|---|---|---|---|"]
    out += ["| %s | `%s` | %s | %s |" % (WORDS.get(c["role"], c["role"]), c["hex"], CONF[c["confidence"]], c["why"])
            for c in r["colors"]]
    out += ["", "## Шрифты", ""] + ["- %s: %s%s" % ("заголовки" if f["use"] == "heading" else "текст", f["name"],
                                                    "" if f["loaded"] else " (системный или не загружен)")
                                    for f in t["families"]]
    out += ["- кегли: %s" % ", ".join("%spx" % x["px"] for x in t["scale"]) or "—",
            "- насыщенность: %s" % ", ".join(x["weight"] for x in t["weights"][:5]),
            "- межстрочный: %s" % ", ".join(str(x["ratio"]) for x in t["lineHeights"][:4]), "", "## Форма и ритм", "",
            "- отступы: %s%s" % (", ".join("%dpx" % x["px"] for x in r["spacing"]) or "—",
                                 " (шаг %dpx)" % r["spacingBase"] if r["spacingBase"] else ""),
            "- скругления: %s" % (", ".join(x["value"] for x in r["radius"]) or "—"),
            "- тени: %s" % (len(r["shadows"]) and "%d вида" % len(r["shadows"]) or "нет"),
            "- движение: %s; %s" % (", ".join(x["value"] for x in r["motion"]["durations"]) or "—",
                                    ", ".join(x["value"] for x in r["motion"]["easings"][:3]) or "—"),
            "- брейкпоинты: %s" % (", ".join("%dpx" % x["px"] for x in r["breakpoints"]) or "—"), "",
            "## Кнопки и поля", ""]
    for b in r["components"]["buttons"]:
        out.append("- кнопка `%s` на `%s`, скругление %s%s" % (b.get("color"), b.get("bg"), b.get("radius"), "".join(
            "; %s: %s" % ({"hover": "под курсором", "focus": "фокус"}[k], ", ".join("%s %s" % kv for kv in v.items()))
            for k, v in b["states"].items())))
    out += ["- поле: рамка %s, фокус: %s" % (i.get("borderColor"), i["states"].get("focus") or "без изменений")
            for i in r["components"]["inputs"]]
    if r.get("dark"):
        out += ["", "## Тёмная тема", "", "есть: фон `%s`" % next(c["hex"] for c in r["dark"]["colors"])
                if r["dark"]["differs"] else "сайт не меняется в тёмной теме"]
    out += ["", "## Не наблюдалось", "", ", ".join(r["missing"]) or "всё основное найдено", "",
            "Черновик токенов — `tokens.css` рядом; в проект — после того, как человек посмотрел.", ""]
    return "\n".join(out)
