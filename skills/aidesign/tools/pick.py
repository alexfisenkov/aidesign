#!/usr/bin/env python3
"""Справочник AI Design: подбор стиля, палитры, шрифтовой пары и паттерна лендинга.

    python3 pick.py "кофейня уютная" [--industry ID] [--mood …] [--dark] [--n 3] [--tokens OUT] [--json]
    python3 pick.py validate [--json]
    python3 pick.py list styles|palettes|pairs|industries|landings|fonts [--json]
    python3 pick.py make-palette --id ID --name … --bg … --text … --primary … --accent … [--dark-first]

Данные — `knowledge/справочник/*.json` (по умолчанию рядом со скиллом; `--data DIR` или
переменная AIDESIGN_REFERENCE подменяют). Отрасль — стартовая гипотеза: слова и вкус
человека главнее (`knowledge/язык/решения-споров.md`, спор 7). Узнаётся по главному слову дела
(«юрист по семейным делам» — юрист): вес совпадений, существительное важнее определения, фраза
отрасли — только целиком и без разрыва предлогом (`detect_industry`). Правила отраслей — закрытая
грамматика: условие из CONDITIONS → действия `style:`, `pattern:`, `mode:`, `constraint:`,
`mood:`; данные ничего не исполняют. Тёмная тема выводится из светлой (`derive_dark`), если
у палитры нет своей. `validate` проверяет контраст (текст 4.5:1, рамки и фокус 3:1, обе
темы), цвета каждой темы через check.py (находки шаблонности), кириллицу у обоих шрифтов
пары, ссылки Google Fonts, дубли и ссылки между файлами. `--tokens` не перезаписывает файл
без своей шапки (код 2), заменить его — только с `--force`.
Устройство — по мотивам UI UX Pro Max (MIT), содержание своё. Коды: 0 / 1 нарушения / 2 ввод.
"""

import argparse
import json
import math
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {"styles": "стили.json", "palettes": "палитры.json", "pairs": "шрифты-пары.json",
         "industries": "отрасли.json", "landings": "лендинги.json", "fonts": "google-fonts.json"}
MINIMUM = {"styles": 40, "palettes": 150, "pairs": 80, "industries": 60, "landings": 20}
ROLES = ("bg", "surface", "text", "muted", "border", "divider", "primary", "on-primary", "accent",
         "on-accent", "ring", "danger", "on-danger", "success", "warning", "on-warning")
TEXT_PAIRS = [("text", "bg"), ("text", "surface"), ("muted", "bg"), ("muted", "surface"),
              ("on-primary", "primary"), ("on-accent", "accent"), ("on-danger", "danger"),
              ("on-warning", "warning"), ("success", "bg")]
UI_PAIRS = [("border", "bg"), ("ring", "bg"), ("ring", "surface"), ("primary", "bg")]
TAILWIND = ("#2563EB", "#3B82F6", "#6366F1")
# Закрытая грамматика: условие → основы слов запроса (после stem), действия — пять префиксов.
CONDITIONS = {
    "if_luxury": ("дорог", "премиум", "люкс", "элитн", "роскош", "статусн"),
    "if_budget": ("недорог", "дешев", "эконом", "бюджетн", "доступн"),
    "if_kids": ("дет", "детск", "ребенк", "ребен", "малыш", "школьник", "подростк"),
    "if_trust": ("надежн", "строг", "серьезн", "солидн", "довер", "официальн"),
    "if_warm": ("уют", "уютн", "тепл", "домашн", "семейн", "душевн"),
    "if_bold": ("смел", "дерзк", "ярк", "необычн", "громк", "драйв"),
    "if_calm": ("спокойн", "тих", "мягк", "нежн", "бережн"),
    "if_night": ("вечер", "вечерн", "ноч", "ночн", "бар", "клуб"),
    "if_dark": ("темн", "черн", "мрачн"),
    "if_light": ("светл", "бел", "воздушн"),
    "if_booking": ("запис", "бронир", "брон"),
    "if_reading": ("стат", "стать", "блог", "читат", "лонгрид", "журнал"),
    "if_portfolio": ("портфолио", "работ", "галере", "кейс"),
    "if_eco": ("эко", "натуральн", "природн", "органическ", "фермерск"),
    "if_minimal": ("минимал", "минималистичн", "прост", "чист", "лаконичн"),
    "if_classic": ("классическ", "традиционн", "старинн", "винтажн"),
    "if_modern": ("современн", "модн", "стильн", "свеж"),
    "if_playful": ("весел", "игрив", "забавн", "задорн"),
    "if_tech": ("технологичн", "цифров", "онлайн", "it"),
}
ACTIONS = ("style", "pattern", "mode", "constraint", "mood")
ENDINGS = sorted(("иями ями ами иях ях ах ией ей ой ий ый ая яя ое ее ые ие ого его ому ему ыми ими ую "
                  "юю ом ем ам ям ов ев ия ья ью ье иям ием ии ую ешь ет ют ут ть ться ся сь ы и а я о е у "
                  "ю ь й").split(), key=len, reverse=True)
FALLBACK = {"Serif": "Georgia, \"Times New Roman\", serif", "Sans Serif": "\"Segoe UI\", system-ui, sans-serif",
            "Display": "\"Segoe UI\", system-ui, sans-serif", "Handwriting": "\"Segoe UI\", system-ui, cursive",
            "Monospace": "ui-monospace, Menlo, Consolas, monospace"}
FONT_URL = re.compile(r"^https://fonts\.googleapis\.com/css2\?(family=[A-Za-z0-9+]+(?::wght@[0-9;]+)?&)+display=swap$")


class InputError(Exception):
    pass


# ── цвет: sRGB ↔ OKLab/OKLCH, контраст WCAG ─────────────────────────────────

def hex_rgb(h):
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(h)):
        raise ValueError("не цвет вида #RRGGBB: %s" % h)
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def rgb_hex(c):
    return "#" + "".join("%02X" % round(min(1, max(0, x)) * 255) for x in c)


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def contrast(a, b):
    la, lb = (0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(bb) for r, g, bb in (hex_rgb(a), hex_rgb(b)))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def oklch(h):
    r, g, b = (_lin(x) for x in hex_rgb(h))
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b))
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def _from_oklch(L, C, H):
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l_, m_, s_ = (v ** 3 for v in (L + 0.3963377774 * a + 0.2158037573 * b,
                                   L - 0.1055613458 * a - 0.0638541728 * b, L - 0.0894841775 * a - 1.2914855480 * b))
    return [_gam(v) if v >= 0 else -1 for v in (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
                                                -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
                                                -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)]


def from_oklch(L, C, H):
    """Цвет OKLCH → hex; вне охвата sRGB насыщенность уменьшается до охвата."""
    L = min(1.0, max(0.0, L))
    lo, hi = 0.0, C
    rgb = _from_oklch(L, C, H)
    if all(-1e-4 <= x <= 1 + 1e-4 for x in rgb):
        return rgb_hex(rgb)
    for _ in range(24):
        mid = (lo + hi) / 2
        if all(-1e-4 <= x <= 1 + 1e-4 for x in _from_oklch(L, mid, H)):
            lo = mid
        else:
            hi = mid
    return rgb_hex(_from_oklch(L, lo, H))


def delta_e(a, b):
    (l1, c1, h1), (l2, c2, h2) = oklch(a), oklch(b)
    da = c1 * math.cos(math.radians(h1)) - c2 * math.cos(math.radians(h2))
    db = c1 * math.sin(math.radians(h1)) - c2 * math.sin(math.radians(h2))
    return math.sqrt((l1 - l2) ** 2 + da * da + db * db) * 100


def tailwind_like(h):
    return any(delta_e(h, t) < 10 for t in TAILWIND)


def mix(a, b, t):
    return rgb_hex([x + (y - x) * t for x, y in zip(hex_rgb(a), hex_rgb(b))])


def toward(color, against, need, step=0.01, up=None):
    """Двигать светлоту `color` (OKLCH), пока контраст со всеми `against` не станет ≥ need."""
    L, C, H = oklch(color)
    if up is None:
        up = oklch(against[0])[0] < 0.5
    for _ in range(100):
        c = from_oklch(L, C, H)
        if all(contrast(c, x) >= need for x in against):
            return c
        L += step if up else -step
        if not 0 <= L <= 1:
            break
    return "#FFFFFF" if up else "#000000"


def fade(fg, bg, others, need):
    """Самый близкий к фону оттенок fg→bg, у которого контраст со всеми фонами ещё ≥ need."""
    best = fg
    for i in range(1, 100):
        c = mix(fg, bg, i / 100)
        if all(contrast(c, x) >= need for x in [bg] + others):
            best = c
        else:
            break
    return best


def on_color(fill, candidates):
    return max(candidates, key=lambda c: contrast(c, fill))


def fill_with_text(fill, texts, bgs, need_bg=3.0):
    """Заливка кнопки: контраст с фоном ≥ need_bg и с одним из текстов ≥ 4.5."""
    L, C, H = oklch(fill)
    dark_bg = oklch(bgs[0])[0] < 0.5
    for _ in range(100):
        c = from_oklch(L, C, H)
        on = on_color(c, texts)
        if contrast(on, c) >= 4.5 and all(contrast(c, b) >= need_bg for b in bgs):
            return c, on
        L += 0.01 if dark_bg else -0.01
        if not 0 <= L <= 1:
            break
    raise ValueError("не удалось подобрать заливку для %s" % fill)


def finish(bg, text, primary, accent, surface=None):
    """Полный набор ролей из четырёх опорных цветов; контраст подгоняется светлотой."""
    dark = oklch(bg)[0] < 0.5
    Lb, Cb, Hb = oklch(bg)
    if surface is None:
        surface = from_oklch(Lb + (0.045 if dark else (-0.03 if Lb > 0.975 else 0.025)), Cb, Hb)
    bgs = [bg, surface]
    text = toward(text, bgs, 7.0)
    light_ink = "#FFFFFF" if not dark else from_oklch(0.98, 0.01, Hb)
    texts = [light_ink, text, bg] if not dark else [bg, text, "#FFFFFF"]
    primary, on_primary = fill_with_text(primary, texts, bgs)
    accent, on_accent = fill_with_text(accent, texts, bgs, need_bg=1.0)
    hd = 25 if not dark else 25
    danger, on_danger = fill_with_text(from_oklch(0.52 if not dark else 0.72, 0.17, hd), texts, bgs)
    success = toward(from_oklch(0.5 if not dark else 0.78, 0.12, 150), bgs, 4.6)
    warning, on_warning = fill_with_text(from_oklch(0.8, 0.15, 80), texts, bgs, need_bg=1.0)
    return {"bg": bg, "surface": surface, "text": text, "muted": fade(text, bg, [surface], 4.7),
            "border": fade(text, bg, [surface], 3.1), "divider": mix(bg, text, 0.14),
            "primary": primary, "on-primary": on_primary, "accent": accent, "on-accent": on_accent,
            "ring": toward(primary, bgs, 3.1), "danger": danger, "on-danger": on_danger,
            "success": success, "warning": warning, "on-warning": on_warning}


def derive_dark(light):
    """Тёмная тема из светлой: ступени поверхностей того же оттенка, акценты светлее и тише."""
    _, cb, hb = oklch(light["bg"])
    _, cp, hp = oklch(light["primary"])
    hue = hb if cb > 0.012 else hp
    bg = from_oklch(0.2, min(0.025, max(cb, 0.008)), hue)
    lp, _, _ = oklch(light["primary"])
    la, ca, ha = oklch(light["accent"])
    return finish(bg, from_oklch(0.94, 0.012, hue), quiet(max(lp, 0.72), min(cp, 0.14), hp),
                  quiet(max(la, 0.72), min(ca, 0.14), ha))


def quiet(L, C, H):
    """Акцент тёмной темы без «кислоты»: насыщенность HSL не выше 0.75 (иначе на почти чёрном
    фоне это примета dark-neon из check.py)."""
    import colorsys
    while True:
        h = from_oklch(L, C, H)
        if C <= 0.04 or colorsys.rgb_to_hls(*hex_rgb(h))[2] <= 0.75:
            return h
        C -= 0.01


def make_light(dark):
    """Светлая пара для палитры «сначала тёмная»: те же оттенки на светлом фоне."""
    _, cb, hb = oklch(dark["bg"])
    lp, cp, hp = oklch(dark["primary"])
    _, ca, ha = oklch(dark["accent"])
    return finish(from_oklch(0.975, min(cb, 0.02), hb), from_oklch(0.22, min(cb + 0.01, 0.03), hb),
                  from_oklch(min(lp, 0.5), cp, hp), from_oklch(0.62, ca, ha))


def themes(p):
    return p["light"], p.get("dark") or derive_dark(p["light"])


# ── поиск по-русски ─────────────────────────────────────────────────────────

def stem(word):
    w = re.sub(r"[^a-zа-я0-9-]", "", word.lower().replace("ё", "е"))
    for e in ENDINGS:
        if w.endswith(e) and len(w) - len(e) >= 3:
            return w[:-len(e)]
    return w


def stems(text):
    return [stem(w) for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9-]+", " ".join(text) if isinstance(text, list) else str(text)) if len(w) > 1]


def same(a, b):
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and long_.startswith(short)


def hits(query, words):
    """Слова запроса, которые нашлись среди слов записи."""
    ws = stems(words)
    return [q for q in query if any(same(q, w) for w in ws)]


# ── отрасль: главное слово дела важнее определения ─────────────────────────

PREPOSITIONS = {"по", "у", "для", "с", "со", "в", "во", "на", "о", "об", "обо", "от", "до", "из", "при", "без", "за",
                "под", "над", "к", "ко", "про", "около", "возле", "через", "между", "среди"}
ADJ_ENDINGS = ("ыми", "ими", "ого", "его", "ому", "ему", "ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие",
               "ую", "юю", "ым", "им", "ых", "их")
GENERIC = ("сайт", "лендинг", "страниц", "проект", "компани", "бизнес", "услуг", "открыва", "открою", "хочу", "нуж",
           "мой", "моя", "моё", "мое", "мои", "наш", "свой", "своя", "своё", "свое")
# Слова-рамки: «мастер маникюра», «школа танцев», «салон красоты» — дело называет второе слово.
FRAMES = ("мастер", "школ", "студи", "центр", "салон", "магазин", "клуб", "агентств", "бюро", "кабинет",
          "специалист", "контор")


def query_terms(words):
    """Слова запроса с весом: главное слово дела (первое существительное до предлога) — 3,
    другое существительное — 2, определение и слово-рамка — 1, всё после предлога — вдвое легче,
    общие слова («сайт», «услуги») — 0.25, сам предлог — 0 (нужен только фразам вроде «торт на
    заказ»). chunk — номер куска между предлогами: фраза отрасли не собирается через предлог."""
    terms, chunk = [], 0
    for w in words:
        low = w.lower().replace("ё", "е")
        if low in PREPOSITIONS:
            chunk += 1
            terms.append({"stem": low, "word": low, "weight": 0.0, "free": False, "chunk": chunk})
            continue
        noun = not (len(low) > 3 and low.endswith(ADJ_ENDINGS)) or low.endswith(("ние", "тие", "ния", "тия"))
        generic, frame = low.startswith(GENERIC), low.startswith(FRAMES)
        weight = 0.25 if generic else (2.0 if noun and not frame else 1.0) * (0.5 if chunk else 1.0)
        terms.append({"stem": stem(w), "word": low, "weight": weight, "chunk": chunk,
                      "free": noun and not generic and not frame and not chunk})
    return terms


def industry_phrases(ind):
    """Ключевые слова отрасли и части названия («кафе и столовая» → две фразы) — списками основ."""
    raw = list(ind["keywords"]) + re.split(r",|\s+и\s+", ind["title"])
    out = []
    for s in (stems(p) for p in raw):
        if s and s not in out:
            out.append(s)
    return out


def industry_score(ind, terms):
    """(очки, сколько слов, номера слов). Фраза из нескольких слов засчитывается, только если все её
    слова есть в одном куске запроса: «семейное кафе» не срабатывает на «семейным делам», «детский
    центр» — на «детский стоматолог в центре»."""
    found, bonus = set(), 0.0
    for ps in industry_phrases(ind):
        span = sum(p in PREPOSITIONS for p in ps)            # «торт на заказ» сама проходит через предлог
        for chunk in sorted({t["chunk"] for t in terms}):
            idx = [{i for i, t in enumerate(terms) if chunk <= t["chunk"] <= chunk + span and same(t["stem"], p)}
                   for p in ps]
            if all(idx):
                found |= set().union(*idx)
                bonus += 0.5 if len(ps) > 1 else 0.0
                break
    return sum(terms[i]["weight"] for i in found) + bonus, len(found), found


def detect_industry(industries, words):
    """Лучшая отрасль по весу совпадений; при равенстве — по числу совпавших слов, затем по порядку
    в справочнике. Главное слово дела — первое свободное существительное, которое знает хоть одна отрасль."""
    terms = query_terms(words)
    known = [i for i, t in enumerate(terms) if t["free"] and any(industry_score(ind, [t])[1] for ind in industries)]
    if known:
        terms[known[0]]["weight"] = 3.0
    best, best_key, best_found = None, (0, 0), set()
    for ind in industries:
        score, n, found = industry_score(ind, terms)
        if score > 0 and (score, n) > best_key:
            best, best_key, best_found = ind, (score, n), found
    return best, [terms[i]["word"] for i in sorted(best_found) if terms[i]["weight"] > 0]


# ── данные ──────────────────────────────────────────────────────────────────

def data_dir(arg=None):
    for d in (arg, os.environ.get("AIDESIGN_REFERENCE"), os.path.join(HERE, "..", "knowledge", "справочник"),
              os.path.join(HERE, "справочник")):
        if d and os.path.isfile(os.path.join(d, FILES["styles"])):
            return os.path.abspath(d)
    raise InputError("не нашёл справочник: укажите --data <папка knowledge/справочник скилла>")


def load(d):
    out = {}
    for kind, name in FILES.items():
        with open(os.path.join(d, name), encoding="utf-8") as f:
            raw = json.load(f)
        out[kind] = raw.get("families" if kind == "fonts" else kind, [])
        if kind == "industries":
            out["constraints"] = raw.get("constraints", {})
    return out


def by_id(items, key="id"):
    return {x[key]: x for x in items}


def anchors(d):
    p = os.path.join(d, "..", "язык", "антипаттерны.md")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return set(re.findall(r"\{#([\w-]+)\}", f.read()))


def font_url(pair, fonts):
    parts = []
    for role in ("heading", "body"):
        fam = pair[role]
        if fam in [p.split(":")[0].replace("+", " ") for p in parts]:
            continue
        w = sorted(set(pair["weights"][role] + (pair["weights"]["body"] if pair["body"] == fam and role == "heading" else [])))
        styles = fonts.get(fam, {}).get("styles", [])
        static = styles == ["400"]
        parts.append(fam.replace(" ", "+") + ("" if static else ":wght@" + ";".join(str(x) for x in w)))
    return "https://fonts.googleapis.com/css2?" + "".join("family=%s&" % p for p in parts) + "display=swap"


# ── проверка справочника ────────────────────────────────────────────────────

def parse_rules(rules, ids, constraints):
    """Ошибки грамматики правил отрасли (пустой список — правила верны)."""
    errs = []
    if not isinstance(rules, dict):
        return ["правила должны быть объектом «условие → действия»"]
    for cond, acts in rules.items():
        if cond != "must_have" and cond not in CONDITIONS:
            errs.append("неизвестное условие %s" % cond)
        if not isinstance(acts, list) or not acts or len(acts) != len(set(acts)):
            errs.append("%s: нужен непустой список действий без повторов" % cond)
            continue
        for a in acts:
            prefix, _, val = str(a).partition(":")
            if prefix not in ACTIONS:
                errs.append("%s: неизвестное действие %s" % (cond, a))
            elif prefix == "mode" and val not in ("dark", "light"):
                errs.append("%s: mode только dark или light" % cond)
            elif prefix in ("style", "pattern") and val not in ids[prefix]:
                errs.append("%s: нет %s %s" % (cond, prefix, val))
            elif prefix == "constraint" and val not in constraints:
                errs.append("%s: ограничение %s не описано в constraints" % (cond, val))
    return errs


def validate(d):
    v, db = [], load(d)
    for kind, need in MINIMUM.items():
        if len(db[kind]) < need:
            v.append("%s: %d записей, нужно не меньше %d" % (FILES[kind], len(db[kind]), need))
    for kind in MINIMUM:
        seen = set()
        for x in db[kind]:
            if x.get("id") in seen:
                v.append("%s: повтор id %s" % (FILES[kind], x.get("id")))
            seen.add(x.get("id"))
    fonts, anc = by_id(db["fonts"], "family"), anchors(d)
    fam_dir = os.path.join(d, "..", "язык", "стили")
    for s in db["styles"]:
        if os.path.isdir(fam_dir) and not os.path.isfile(os.path.join(fam_dir, s["family"] + ".md")):
            v.append("стиль %s: нет семейства стили/%s.md" % (s["id"], s["family"]))
        v += ["стиль %s: нет приметы #%s в антипаттерны.md" % (s["id"], a) for a in s.get("avoid", []) if anc is not None and a not in anc]
    seen, blue = set(), []
    for p in db["palettes"]:
        try:
            light, dark = themes(p)
            for mode, roles in (("светлая", light), ("тёмная", dark)):
                miss = [r for r in ROLES if r not in roles]
                if miss:
                    v.append("палитра %s (%s): нет ролей %s" % (p["id"], mode, ", ".join(miss)))
                    continue
                for (fg, bg), need in [(x, 4.5) for x in TEXT_PAIRS] + [(x, 3.0) for x in UI_PAIRS]:
                    r = contrast(roles[fg], roles[bg])
                    if r + 1e-9 < need:
                        v.append("палитра %s (%s): контраст %s/%s %.2f:1 меньше %.1f:1" % (p["id"], mode, fg, bg, r, need))
                if contrast(roles["muted"], roles["bg"]) > contrast(roles["text"], roles["bg"]) + 1e-9:
                    v.append("палитра %s (%s): приглушённый текст контрастнее основного" % (p["id"], mode))
                if 110 < oklch(roles["danger"])[2] < 200:
                    v.append("палитра %s (%s): ошибка окрашена в зелёный" % (p["id"], mode))
        except (ValueError, KeyError) as e:
            v.append("палитра %s: %s" % (p.get("id"), e))
            continue
        key = tuple(light.get(r) for r in ("bg", "text", "primary", "accent"))
        if key in seen:
            v.append("палитра %s: повтор цветов другой палитры" % p["id"])
        seen.add(key)
        if any(tailwind_like(light[r]) for r in ("primary", "accent")):
            blue.append(p["id"])
        if not all(p.get(f) for f in ("name", "mood", "for")):
            v.append("палитра %s: нужны name, mood и for" % p["id"])
    v += palette_findings(db["palettes"])
    if db["palettes"] and len(blue) / len(db["palettes"]) > 0.05:
        v.append("палитры: синих «как Tailwind» %d из %d — больше 5 %%: %s" % (len(blue), len(db["palettes"]), ", ".join(blue)))
    seen = set()
    for p in db["pairs"]:
        if (p["heading"], p["body"]) in seen:
            v.append("пара %s: повтор сочетания %s + %s" % (p["id"], p["heading"], p["body"]))
        seen.add((p["heading"], p["body"]))
        for role in ("heading", "body"):
            f = fonts.get(p[role])
            if not f:
                v.append("пара %s: шрифта %s нет в каталоге кириллических google-fonts.json" % (p["id"], p[role]))
            elif "cyrillic" not in f["subsets"]:
                v.append("пара %s: у %s нет кириллицы" % (p["id"], p[role]))
            elif p.get("license", {}).get(role) != f["license"]:
                v.append("пара %s: лицензия %s не совпадает с каталогом (%s)" % (p["id"], p[role], f["license"]))
            elif any(str(w) not in f["styles"] for w in p["weights"][role]):
                v.append("пара %s: у %s нет начертаний %s" % (p["id"], p[role], p["weights"][role]))
        if not FONT_URL.match(p.get("url", "")) or (all(p[r] in fonts for r in ("heading", "body")) and p["url"] != font_url(p, fonts)):
            v.append("пара %s: ссылка Google Fonts неверного вида (ждём %s)" % (p["id"], font_url(p, fonts) if all(p[r] in fonts for r in ("heading", "body")) else "css2?family=…&display=swap"))
    ids = {"style": {s["id"] for s in db["styles"]}, "pattern": {x["id"] for x in db["landings"]}}
    pal, pairs = {p["id"] for p in db["palettes"]}, {p["id"] for p in db["pairs"]}
    for i in db["industries"]:
        name = "отрасль %s" % i["id"]
        v += ["%s: нет стиля %s" % (name, x) for x in i["styles"] if x not in ids["style"]]
        v += ["%s: нет палитры %s" % (name, x) for x in i["palettes"] if x not in pal]
        v += ["%s: нет пары %s" % (name, x) for x in i["pairs"] if x not in pairs]
        v += ["%s: нет паттерна %s" % (name, i["landing"])] if i["landing"] not in ids["pattern"] else []
        v += ["%s: нет приметы #%s" % (name, a) for a in i.get("avoid", []) if anc is not None and a not in anc]
        v += ["%s: %s" % (name, e) for e in parse_rules(i.get("rules", {}), ids, db["constraints"])]
        fam = {s["id"]: s["family"] for s in db["styles"]}
        grp = {p["id"]: p["group"] for p in db["palettes"]}
        spread = (len({fam.get(x) for x in i["styles"]}), len({grp.get(x) for x in i["palettes"]}), len(set(i["pairs"])))
        if min(spread) < 3:
            v.append("%s: для трёх разных превью нужны стили из трёх семейств, палитры из трёх групп и три пары (сейчас %d/%d/%d)"
                     % ((name,) + spread))
    for x in db["landings"]:
        if len(x.get("sections", [])) < 3 or not x.get("cta"):
            v.append("лендинг %s: нужны разделы (от трёх) и место кнопки" % x["id"])
    return v


# ── подбор ──────────────────────────────────────────────────────────────────

def apply_rules(rules, q):
    out = {"activated": [], "style": [], "constraint": [], "pattern": None, "mode": None, "mood": []}
    for cond, acts in rules.items():
        found = [w for w in q if any(same(w, s) for s in CONDITIONS.get(cond, ()))]
        if cond != "must_have" and not found:
            continue
        out["activated"].append({"condition": cond, "words": found, "actions": acts})
        for a in acts:
            prefix, _, val = a.partition(":")
            if prefix in ("pattern", "mode"):
                out[prefix] = val
            elif val not in out[prefix]:
                out[prefix].append(val)
    return out


def rank(items, q, hyp, boost, why_hyp, why_rule, fields, orig=None):
    scored = []
    for x in items:
        score, reasons = 0.0, []
        if x["id"] in hyp:
            score += 3 - hyp.index(x["id"]) * 0.4
            reasons.append(why_hyp)
        if x["id"] in boost:
            score += 4
            reasons.append(why_rule)
        h = sorted(set(hits(q, [str(x.get(f, "")) if not isinstance(x.get(f), list) else " ".join(x[f]) for f in fields])))
        if h:
            score += 2 * len(h)
            reasons.append("совпали слова запроса: %s" % ", ".join(sorted({(orig or {}).get(w, w) for w in h})))
        if score:
            scored.append((score, x, reasons))
    scored.sort(key=lambda t: -t[0])
    return scored


def diverse(scored, key, n, pool):
    """Лучшие n с разным ключом; не хватило — добор из всего справочника ради разных превью."""
    out, used = [], set()
    rest = [(0, x, ["другое направление для разнообразия превью (не из отрасли и не по словам)"]) for x in pool]
    for s, x, r in scored + rest:
        if len(out) == n:
            break
        if key(x) not in used:
            out.append(dict(x, reasons=r, score=round(s, 2)))
            used.add(key(x))
    return out


def pick(query, d, industry=None, moods=(), dark=False, n=3):
    db = load(d)
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9-]+", query + " " + " ".join(moods))
    q = [stem(w) for w in words if len(w) > 1]
    orig = {stem(w): w.lower() for w in words}
    inds = by_id(db["industries"])
    if industry:
        if industry not in inds:
            raise InputError("нет отрасли %s (список: pick.py list industries)" % industry)
        ind, ind_hits = inds[industry], ["--industry"]
    else:
        ind, ind_hits = detect_industry(db["industries"], re.findall(r"[A-Za-zА-Яа-яЁё0-9-]+", query + " " + " ".join(moods)))
    rules = apply_rules(ind.get("rules", {}), q) if ind else apply_rules({}, q)
    mode = "dark" if dark else (rules["mode"] or "light")
    mq = q + [stem(m) for m in rules["mood"]]
    t = "отрасль «%s»: стартовая гипотеза" % ind["title"] if ind else ""
    styles = diverse(rank(db["styles"], mq, ind["styles"] if ind else [], rules["style"], t, "правило отрасли по словам запроса",
                          ("title", "tags", "fits", "summary"), orig), lambda x: x["family"], n, db["styles"])
    night = [p["id"] for p in db["palettes"] if p.get("prefer") == "dark"] if mode == "dark" else []
    pals = diverse(rank(db["palettes"], mq, ind["palettes"] if ind else [], night, t, "тёмная тема: палитра задумана тёмной",
                        ("name", "mood", "for", "tags"), orig), lambda x: x["group"], n, db["palettes"])
    pairs = diverse(rank(db["pairs"], mq, ind["pairs"] if ind else [], [], t, "", ("name", "character", "for", "tags"), orig),
                    lambda x: x["heading"], n, db["pairs"])
    land_h = [rules["pattern"]] if rules["pattern"] else ([ind["landing"]] if ind else [])
    lands = diverse(rank(db["landings"], mq, land_h, [], t or "паттерн по правилу отрасли", "", ("title", "when", "tags"), orig),
                    lambda x: x["id"], n, db["landings"])
    for p in pals:
        p["light"], p["dark"] = themes(p)
    fonts = by_id(db["fonts"], "family")
    for p in pairs:
        p["fallback"] = {r: FALLBACK.get(fonts.get(p[r], {}).get("category"), FALLBACK["Sans Serif"]) for r in ("heading", "body")}
    k = min(len(styles), len(pals), len(pairs)) or 0
    return {"query": query, "mode": mode, "industry": {"id": ind["id"], "title": ind["title"], "words": ind_hits,
                                                        "avoid": ind.get("avoid", []), "note": ind.get("note", "")} if ind else None,
            "hypothesis": "Отрасль и подбор — стартовая гипотеза; слова человека, интервью и вкус главнее (спор 7).",
            "rules": rules["activated"], "constraints": [{"id": c, "text": db["constraints"].get(c, "")} for c in rules["constraint"]],
            "styles": styles, "palettes": pals, "pairs": pairs, "landings": lands,
            "directions": [{"style": styles[i], "palette": pals[i], "pair": pairs[i]} for i in range(k)]}


# ── вывод ───────────────────────────────────────────────────────────────────

TOKENS_MARK = "Черновик токенов AI Design из справочника"


def own_tokens(path):
    """Файл написан pick.py: шапка-черновик в первых строках."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return TOKENS_MARK in f.read(400)
    except OSError:
        return False


def palette_findings(palettes):
    """Цвета каждой палитры через check.py — светлая и тёмная тема отдельно, как их видит страница.

    Обе темы в одном файле check.py не различает (кремовый фон светлой и терракота тёмной дают
    ложную находку), поэтому каждая тема — свой :root."""
    path = os.path.join(HERE, "check.py")
    if not os.path.isfile(path):
        return ["палитры: нет check.py рядом с pick.py — шаблонность токенов не проверена"]
    import importlib.util
    import shutil
    import tempfile
    spec = importlib.util.spec_from_file_location("aidesign_check_for_pick", path)
    check = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = check
    sys.path.insert(0, HERE)
    try:
        spec.loader.exec_module(check)
    finally:
        sys.path.remove(HERE)
    tmp = tempfile.mkdtemp(prefix="pick-validate-")
    try:
        names = {}
        for p in palettes:
            try:
                light, dark = themes(p)
            except (ValueError, KeyError):
                continue
            for mode, roles in (("светлая", light), ("тёмная", dark)):
                if any(r not in roles for r in ROLES):
                    continue
                f = os.path.join(tmp, "%d.css" % len(names))
                with open(f, "w", encoding="utf-8") as out:
                    out.write(":root {\n%s\n}\n" % "\n".join("  --color-%s: %s;" % (r, roles[r]) for r in ROLES))
                names[os.path.basename(f)] = (p["id"], mode)
        found = check.scan([tmp], use_config=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = []
    for x in found:
        pid, mode = names.get(os.path.basename(str(x.path)), ("?", "?"))
        out.append("палитра %s (%s): check.py находит [%s] %s" % (pid, mode, x.rule, x.message))
    return out


def tokens_css(res, direction=0):
    d = res["directions"][direction]
    s, p, f = d["style"], d["palette"], d["pair"]
    tk = s.get("tokens", {})
    first, second = (p["dark"], p["light"]) if res["mode"] == "dark" else (p["light"], p["dark"])
    lines = ["/* " + TOKENS_MARK + " — стартовая гипотеза, не решение.",
             "   Стиль: %s (%s). Палитра: %s. Шрифты: %s + %s." % (s["title"], s["family"], p["name"], f["heading"], f["body"]),
             "   Подключение шрифтов: %s */" % f["url"], ":root {"]
    lines += ["  --color-%s: %s;" % (r, first[r]) for r in ROLES]
    lines += ['  --font-display: "%s", %s;' % (f["heading"], f["fallback"]["heading"]),
              '  --font-body: "%s", %s;' % (f["body"], f["fallback"]["body"])]
    lines += ["  --radius-%s: %s;" % kv for kv in tk.get("radius", {"s": "6px", "m": "12px", "l": "20px"}).items()]
    unit = int(tk.get("space", 8))
    lines += ["  --space-%d: %dpx;" % (i + 1, unit * m) for i, m in enumerate((1, 2, 3, 4, 6, 8, 12))]
    if s["family"] == "необрутализм":
        lines += ["  /* aidesign-ignore: hard-offset-shadow — стиль необрутализм, записать в DESIGN.md */"]
    lines += ["  --shadow-card: %s;" % tk.get("shadow", "0 1px 2px rgb(0 0 0 / .06), 0 4px 16px rgb(0 0 0 / .06)")]
    lines += ["  --motion-%s: %s;" % kv for kv in tk.get("motion", {"fast": "150ms", "base": "240ms", "ease": "cubic-bezier(.2, 0, 0, 1)"}).items()]
    lines += ["}", ""]
    if res["mode"] == "dark":
        lines += ['[data-theme="light"] {'] + ["  --color-%s: %s;" % (r, second[r]) for r in ROLES] + ["}"]
    else:
        lines += ['[data-theme="dark"] {'] + ["  --color-%s: %s;" % (r, second[r]) for r in ROLES] + ["}", "",
                  "@media (prefers-color-scheme: dark) {", "  :root:not([data-theme]) {"]
        lines += ["    --color-%s: %s;" % (r, second[r]) for r in ROLES] + ["  }", "}"]
    return "\n".join(lines) + "\n"


def human(res):
    out = ["Запрос: %s" % res["query"]]
    ind = res["industry"]
    out.append("Отрасль: %s (по словам: %s)" % (ind["title"], ", ".join(ind["words"])) if ind else "Отрасль не узнана — подбор только по словам.")
    out.append(res["hypothesis"])
    for a in res["rules"]:
        out.append("  правило %s → %s" % (a["condition"], ", ".join(a["actions"])))
    for c in res["constraints"]:
        out.append("  помнить: %s" % c["text"])
    for title, kind, show in (("Стили", "styles", lambda x: "%s — %s" % (x["title"], x["family"])),
                              ("Палитры", "palettes", lambda x: "%s — %s" % (x["name"], x["mood"])),
                              ("Шрифтовые пары", "pairs", lambda x: "%s + %s — %s" % (x["heading"], x["body"], x["character"])),
                              ("Паттерны лендинга", "landings", lambda x: "%s: %s" % (x["title"], " → ".join(x["sections"])))):
        out.append("\n%s:" % title)
        for x in res[kind]:
            out.append("  • %s [%s]\n    почему: %s" % (show(x), x["id"], "; ".join(x["reasons"])))
    out.append("\nТри направления для превью (разные семейства):")
    for i, dct in enumerate(res["directions"]):
        out.append("  %s) %s · %s · %s + %s" % ("абв"[i] if i < 3 else i + 1, dct["style"]["title"], dct["palette"]["name"],
                                              dct["pair"]["heading"], dct["pair"]["body"]))
    if ind and ind["avoid"]:
        out.append("\nНе делать (антипаттерны.md): " + ", ".join("#" + a for a in ind["avoid"]))
    return "\n".join(out)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv and argv[0] in ("validate", "list", "make-palette") else "pick"
    ap = argparse.ArgumentParser(prog="pick.py", description="Справочник AI Design: подбор и проверка")
    ap.add_argument("--data")
    ap.add_argument("--json", action="store_true")
    if cmd == "pick":
        ap.add_argument("query")
        ap.add_argument("--industry")
        ap.add_argument("--mood", action="append", default=[])
        ap.add_argument("--dark", action="store_true")
        ap.add_argument("--n", type=int, default=3)
        ap.add_argument("--tokens")
        ap.add_argument("--direction", type=int, default=1)
        ap.add_argument("--force", action="store_true")
    else:
        ap.add_argument("cmd")
    if cmd == "list":
        ap.add_argument("kind", choices=sorted(FILES))
    if cmd == "make-palette":
        for f in ("--id", "--name", "--bg", "--text", "--primary", "--accent"):
            ap.add_argument(f, required=True)
        ap.add_argument("--dark-first", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if cmd == "make-palette":
            roles = finish(a.bg, a.text, a.primary, a.accent)
            p = {"id": a.id, "name": a.name, "light": make_light(roles) if a.dark_first else roles}
            if a.dark_first:
                p["dark"] = roles
            print(json.dumps(p, ensure_ascii=False, indent=1))
            return 0
        d = data_dir(a.data)
        if cmd == "validate":
            v = validate(d)
            print(json.dumps({"count": len(v), "violations": v}, ensure_ascii=False, indent=1) if a.json
                  else "\n".join(v + ["Нарушений: %d" % len(v)]))
            return 1 if v else 0
        if cmd == "list":
            items = load(d)[a.kind]
            if a.kind == "palettes":
                items = [dict(p, light=themes(p)[0], dark=themes(p)[1]) for p in items]
            key = "family" if a.kind == "fonts" else "id"
            print(json.dumps({"kind": a.kind, "items": items}, ensure_ascii=False, indent=1) if a.json
                  else "\n".join("%s — %s" % (x[key], x.get("title") or x.get("name") or x.get("category", "")) for x in items))
            return 0
        if a.n < 1 or not a.query.strip():
            raise InputError("нужен запрос словами и --n от 1")
        res = pick(a.query, d, a.industry, a.mood, a.dark, a.n)
        if a.tokens:
            if not 1 <= a.direction <= len(res["directions"]):
                raise InputError("--direction от 1 до %d" % len(res["directions"]))
            out = os.path.join(a.tokens, "tokens.css") if os.path.isdir(a.tokens) else a.tokens
            if os.path.exists(out) and not a.force and not own_tokens(out):
                raise InputError("%s уже есть и написан не справочником — не перезаписываю. Укажите другой путь "
                                 "(например, .aidesign-work/<dir>/pick/tokens.css) или добавьте --force, "
                                 "если файл точно можно заменить" % out)
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(tokens_css(res, a.direction - 1))
            res["tokens"] = out
        print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else human(res) + ("\n\nТокены: %s" % res["tokens"] if a.tokens else ""))
        return 0
    except (InputError, ValueError, OSError, json.JSONDecodeError) as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
