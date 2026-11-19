# По мотивам: pbakaus/impeccable (Apache-2.0) — crates/foundation/src/registry.rs, crates/detect/src/regex_matchers.rs,
# crates/core/src/checks/*; код написан заново, пороги взяты из источника, русский словарь — свой.
"""Правила паритета с Impeccable, которые видны по тексту файла: CSS-объявления и видимый текст.

build(core) отдаёт список Rule для check.RULES; core — сам модуль check.py (без циклического
импорта). Правила, которым нужен каскад и дерево разметки, — в check_cascade.py.
"""

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import check_cascade

Hit = Tuple[int, str]


def _px(value: str) -> List[float]:
    out = []
    for n, unit in re.findall(r"(-?\d*\.?\d+)(px|rem)\b", value):
        out.append(float(n) * (16 if unit == "rem" else 1))
    return out


def _blocks(doc):
    blocks = {}
    for d in doc.decls:
        blocks.setdefault(d.block, []).append(d)
    return blocks.values()


# ---------- рамки и тени ----------

def c_border_accent_rounded(core, doc) -> List[Hit]:
    hits = []
    for ds in _blocks(doc):
        radius = [d for d in ds if d.prop == "border-radius" and not re.fullmatch(r"0(px|%)?|none", d.value.strip())]
        if not radius:
            continue
        for d in ds:
            m = re.fullmatch(r"border-(top|bottom)", d.prop)
            if not m:
                continue
            w = re.search(r"(\d*\.?\d+)px", d.value)
            tw = d.origin == "tw"
            accent = "var(" in d.value or ("tw(" in d.value and not re.search(r"tw\((slate|gray|zinc|neutral|stone)-", d.value)) \
                or any(core.chromatic(c) for c in core.colors_in(d.value))
            if w and "solid" in d.value and accent and float(w.group(1)) >= (1 if tw else 3):
                hits.append((d.line, "%s %s" % (d.prop, d.value)[:40]))
    return hits


def shadow_blur(core, value: str, min_alpha: float = 0.12) -> float:
    best = 0.0
    for layer in core.split_layers(value):
        if "inset" in layer:
            continue
        cols = re.findall(r"(?:rgba?|hsla?)\([^)]*\)|#[0-9a-fA-F]{3,8}\b", layer)
        alpha = 1.0
        if cols:
            nums = re.findall(r"[\d.]+%?", cols[0])
            if cols[0].startswith(("rgba", "hsla")) and len(nums) >= 4:
                alpha = float(nums[3].rstrip("%")) / (100 if nums[3].endswith("%") else 1)
            elif cols[0].startswith("#") and len(cols[0]) in (5, 9):
                alpha = int(cols[0][-2:] if len(cols[0]) == 9 else cols[0][-1] * 2, 16) / 255
        lens = [float(n) * (16 if u == "rem" else 1)
                for n, u in re.findall(r"(-?\d*\.?\d+)(px|rem)?(?![\w(%.])", core.COLOR_RE.sub(" ", layer))]
        if len(lens) >= 3 and alpha >= min_alpha:
            best = max(best, lens[2])
    return best


def c_thin_border_wide_shadow(core, doc) -> List[Hit]:
    """Файл стилей без разметки: правило с рамкой до 1px и тенью от 16px. Страницы — по каскаду."""
    if doc.markup.strip():
        return check_cascade.thin_border_row(core, doc)
    hits = []
    for ds in _blocks(doc):
        border = [d for d in ds if d.prop in {"border", "border-width"} and re.match(r"\s*(0?\.\d+|1)px\b", d.value)
                  and "none" not in d.value and "transparent" not in d.value]
        shadow = [d for d in ds if d.prop == "box-shadow" and shadow_blur(core, d.value) >= 16]
        if border and shadow:
            hits.append((shadow[0].line, ds[0].selector[:40]))
    return hits


def c_buried_raster(core, doc) -> List[Hit]:
    hits = []
    for ds in _blocks(doc):
        if any(d.prop in {"background-blend-mode", "mix-blend-mode"} and d.value.strip() != "normal" for d in ds):
            continue
        for d in ds:
            if d.prop in {"background", "background-image"} and "url(" in d.value:
                head = d.value[:d.value.index("url(")]
                for g in re.findall(r"(?:repeating-)?(?:linear|radial|conic)-gradient\((?:[^()]|\([^()]*\))*\)", head):
                    alphas = [float(a[:-1]) / 100 if a.endswith("%") else float(a)
                              for a in re.findall(r"(?:rgba|hsla)\([^)]*?[,/]\s*([\d.]+%?)\s*\)", g)]
                    alphas += [int(h[-2:], 16) / 255 if len(h) == 9 else 1.0 for h in re.findall(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b", g)]
                    if alphas and min(alphas) >= 0.9:
                        hits.append((d.line, "картинка под плотной заливкой"))
                        break
        opac = [d for d in ds if d.prop == "opacity" and re.fullmatch(r"0?\.\d+", d.value.strip())
                and 0 < float(d.value) <= 0.1]
        if not opac:
            continue
        owner = ds[0].owner
        has_url = any("url(" in d.value for d in ds if d.prop.startswith("background"))
        is_img = doc.text[owner:owner + 4].lower() == "<img" if owner >= 0 \
            else bool(re.search(r"(^|[\s>])img\b[^\s>]*$", ds[0].selector))
        if has_url or is_img:
            hits.append((opac[0].line, "картинка почти прозрачна"))
    return hits


def _rectilinear(points: List[List[str]]) -> bool:
    return len(points) >= 3 and all(a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:] + points[:1]))


def c_organic_clip(core, doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop not in {"clip-path", "-webkit-clip-path"}:
            continue
        m = re.search(r"polygon\(([^)]*(?:\([^)]*\)[^)]*)*)\)", d.value)
        if m:
            pts = [p.split() for p in core.split_layers(m.group(1)) if p.strip() and p.strip() not in {"nonzero", "evenodd"}]
            pts = [[re.sub(r"^0(px|%)?$", "0", x) for x in p] for p in pts if len(p) == 2]
            if len(pts) >= 10 and not _rectilinear(pts):
                hits.append((d.line, "polygon из %d точек" % len(pts)))
        m = re.search(r"path\(\s*[\"']([^\"']*)[\"']", d.value)
        if m and re.search(r"[CSQTAcsqta]", m.group(1)):
            hits.append((d.line, "кривая path()"))
    return hits


SVG_PRIMITIVE = re.compile(r"<(circle|ellipse|rect|polygon|line|polyline)\b", re.I)
SVG_DRAWN = re.compile(r"<(circle|ellipse|rect|polygon|line|polyline|path)\b", re.I)


def c_shape_illustration(core, doc) -> List[Hit]:
    hits = []
    for m in re.finditer(r"<svg\b([^>]*)>(.*?)</svg>", doc.markup, re.S | re.I):
        open_tag, body = m.group(1), m.group(2)
        if len(re.findall(r"<text\b", body, re.I)) > 2 or re.search(r"<pattern\b", body, re.I):
            continue
        painted = re.sub(r"<defs\b.*?</defs>", "", body, flags=re.S | re.I)
        prim, drawn = len(SVG_PRIMITIVE.findall(painted)), len(SVG_DRAWN.findall(painted))
        if prim < 8 or prim < drawn * 0.5:
            continue
        vb = re.search(r"viewBox\s*=\s*[\"']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", open_tag)
        def dim(name, fallback):
            m = re.search(r"\s%s\s*=\s*[\"']?([\d.]+)(px|r?em)?[\"'\s>/]" % name, open_tag)
            if not m:
                return fallback
            return float(m.group(1)) * (16 if m.group(2) in {"em", "rem"} else 1)   # em — размер строки текста
        w = dim("width", float(vb.group(1)) if vb else 0)
        h = dim("height", float(vb.group(2)) if vb else 0)
        fills = {f.lower() for f in re.findall(r"fill\s*[=:]\s*[\"']?([#\w(),.\s%]+?)[\"';\s/>]", body)
                 if f.lower() not in {"none", "transparent", "currentcolor", "inherit"}}
        if w >= 200 and h >= 200 and len(fills) >= 3:
            hits.append((doc.line_of(m.start()), "%d фигур, %d цветов" % (prim, len(fills))))
    return hits


# ---------- ритм ----------

def c_monotonous_spacing(core, doc) -> List[Hit]:
    vals: List[Tuple[float, int]] = []
    for d in doc.decls:
        if re.fullmatch(r"(padding|margin)(-[\w-]+)?|(row-|column-)?gap", d.prop):
            for v in _px(d.value):
                if 0 < v < 200 or d.prop.endswith("gap"):
                    vals.append((round(v / 4) * 4, d.line))
    if len(vals) < 10:
        return []
    counts = {}
    for v, _ in vals:
        counts[v] = counts.get(v, 0) + 1
    dom, n = max(counts.items(), key=lambda kv: kv[1])
    unique = [v for v in counts if v > 0]
    if dom == 0 or n / len(vals) <= 0.6 or len(unique) > 3:
        return []
    line = next(ln for v, ln in vals if v == dom)
    return [(line, "~%gpx в %d из %d отступов" % (dom, n, len(vals)))]


# ---------- текст ----------

def _text(doc) -> str:
    t = re.sub(r"&mdash;|&#0*8212;|&#[xX]0*2014;", "—", doc.visible)
    return t


def c_em_dash(core, doc) -> List[Hit]:
    text = _text(doc)
    latin, cyr = len(re.findall(r"[A-Za-z]", text)), len(re.findall(r"[А-Яа-яЁё]", text))
    if cyr >= latin:                       # в русском тире — грамматика (антипаттерны.md#em-dash)
        return []
    dashes = [m.start() for m in re.finditer(r"—|(?<=\w) -- (?=\w)", text)]
    size = len(" ".join(text.split()))
    if len(dashes) < 8 or size > len(dashes) * 500:
        return []
    return [(doc.line_of(dashes[0]), "%d тире на %d знаков" % (len(dashes), size))]


APHORISM = [
    re.compile(r"\bNot an? [a-z][^.!?<>]{1,40}[.!]\s+[A-Z][^.!?<>]{1,60}[.!]"),
    re.compile(r"\b[A-Z][^.!?<>]{4,80}[.!]\s+(?:No|Just)\s+[a-z][^.!?<>]{2,60}[.!]"),
    re.compile(r"(?<![\w-])Не [а-яё][^.!?<>]{1,40}[.!]\s+[А-ЯЁ][^.!?<>]{1,60}[.!]"),
    re.compile(r"(?<![\w-])[А-ЯЁ][^.!?<>]{4,80}[.!]\s+(?:Без|Никаких|Просто|Только)\s+[а-яё][^.!?<>]{2,60}[.!]"),
    re.compile(r"(?<![\w-])[Ээ]то не просто [^.!?,<>]{1,40}[,—–-]+\s*(?:это|а)\s+[^.!?<>]{1,60}[.!]"),
]


def c_aphoristic(core, doc) -> List[Hit]:
    text = doc.visible
    found = sorted(m.start() for rx in APHORISM for m in rx.finditer(text))
    if len(found) < 3:
        return []
    return [(doc.line_of(found[0]), "%d рубленых конструкций" % len(found))]


THEATER_EN = ("accessibility|accountability|agile|alignment|compliance|diversity|engagement|governance|growth|"
              "hiring|hygiene|innovation|inclusion|kindness|leadership|metrics|privacy|process|productivity|"
              "quality|safety|security|strategy|sustainability|transparency|trust|wellness")
THEATER_RU = ("безопасност|продуктивност|процесс|метрик|качеств|прозрачност|довери|рост|инноваци|вовлеч[её]нност|"
              "заботы|приватност|найм|стратеги|лидерств|соответстви|эффективност|agile|эджайл|инклюзивност|"
              "отч[её]тност|контрол")
THEATER = re.compile(r"\b(?:%s)\s+theat(?:er|re)\b|(?<![\w-])театр\w*\s+(?:%s)[а-яё]*|"
                     r"(?<![\w-])(?:%s)[а-яё]*\s*[—–-]\s*(?:это\s+)?(?:просто\s+|всего лишь\s+)?театр\b"
                     % (THEATER_EN, THEATER_RU, THEATER_RU), re.I)


def c_theater(core, doc) -> List[Hit]:
    return [(doc.line_of(m.start()), m.group(0)[:40]) for m in THEATER.finditer(doc.visible)]


# ---------- дизайн-система ----------

@lru_cache(maxsize=64)
def _scale(folder: str) -> Tuple[Optional[str], tuple, tuple]:
    """(папка design-system, радиусы px, кегли px) по ближайшему design-system/tokens.css выше."""
    for d in [Path(folder)] + list(Path(folder).parents):
        t = d / "design-system" / "tokens.css"
        if t.is_file():
            text = t.read_text(encoding="utf-8", errors="replace")
            radii, sizes = set(), set()
            for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", text):
                if name.startswith("--radius"):
                    radii.update(_px(value))
                elif re.match(r"--(font-size|text|fs|size-text)", name) or (name.startswith("--font-") and _px(value)):
                    sizes.update(_px(value))
            return str(t.parent), tuple(sorted(radii)), tuple(sorted(sizes))
    return None, (), ()


def _ds_check(core, doc, props, which, minimum) -> List[Hit]:
    ds_dir, radii, sizes = _scale(str(Path(doc.path).resolve().parent))
    scale = radii if which == "radius" else sizes
    if not ds_dir or len(scale) < minimum or Path(ds_dir) in Path(doc.path).resolve().parents:
        return []
    hits = []
    for d in doc.decls:
        if d.prop not in props or "var(" in d.value or re.search(r"clamp\(|calc\(|min\(|max\(", d.value):
            continue
        for v in _px(d.value):
            if v == 0 or v >= 999 or any(abs(v - s) < 0.5 for s in scale):
                continue
            hits.append((d.line, "%gpx нет в шкале %s" % (v, "/".join("%g" % s for s in scale))))
            break
    return hits


RADIUS_PROPS = {"border-radius", "border-top-left-radius", "border-top-right-radius",
                "border-bottom-left-radius", "border-bottom-right-radius"}


def build(core) -> list:
    R = core.R

    def bind(fn):
        return lambda doc: fn(core, doc)

    rules = [
        R("border-accent-on-rounded", "side-stripe", "толстая цветная рамка сверху или снизу у скруглённого блока",
          "убрать рамку или скругление; акцент — тоном фона или заголовком", bind(c_border_accent_rounded)),
        R("gpt-thin-border-wide-shadow", "ghost-card", "у ряда карточек и тонкая рамка, и широкая тень",
          "одно из двух: рамка или тень", bind(c_thin_border_wide_shadow)),
        R("buried-raster", "buried-raster", "картинка не доходит до экрана: под плотной заливкой или почти прозрачна",
          "показать материал или убрать его", bind(c_buried_raster)),
        R("organic-clip-path", "geometric-mask", "рваный край или силуэт нарисован clip-path",
          "вырезанный файл или кадр без обрезки", bind(c_organic_clip)),
        R("shape-assembled-illustration", "shape-illustration", "крупная SVG-сцена из простых фигур",
          "настоящая иллюстрация или фото; SVG — для схем и иконок", bind(c_shape_illustration), True),
        R("monotonous-spacing", "monotonous-spacing", "почти везде один и тот же отступ",
          "тесно внутри группы, щедро между группами (сетка-и-ритм.md)", bind(c_monotonous_spacing)),
        R("em-dash-overuse", "em-dash", "тире в каждом предложении английского текста",
          "запятые, двоеточия, скобки", bind(c_em_dash), True),
        R("aphoristic-cadence", "copy-shapes", "рубленые афоризмы «Не X. Y.» раз за разом",
          "обычное предложение: имя и утверждение", bind(c_aphoristic), True),
        R("theater-slop-phrase", "theater-phrase", "«театр безопасности» и подобные ярлыки",
          "прямо сказать, что вещь делает или не делает", bind(c_theater), True),
        R("design-system-radius", "design-system-drift", "скругление мимо шкалы design-system",
          "радиус из токенов --radius-* или добавить ступень в tokens.css",
          lambda doc: _ds_check(core, doc, RADIUS_PROPS, "radius", 1)),
        R("design-system-font-size", "design-system-drift", "кегль мимо шкалы design-system",
          "размер из токенов или добавить ступень в tokens.css",
          lambda doc: _ds_check(core, doc, {"font-size"}, "size", 2)),
    ]
    return rules + check_cascade.build(core)
