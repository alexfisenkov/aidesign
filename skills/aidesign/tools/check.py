#!/usr/bin/env python3
# По мотивам: pbakaus/impeccable antipatterns (Apache-2.0) — crates/live/assets/antipatterns.json; код написан заново.
# Совпадают id правил: blinking-cursor, bounce-easing, gradient-text, hard-offset-shadow, justified-text,
# marquee, overused-font, pulsing-dot, skipped-heading, tight-leading, tiny-text, wide-tracking.
"""Проверка шаблонности: ищет в HTML и CSS приметы типового ИИ-дизайна.

Запуск:  python3 check.py <файл или папка>… [--json] [--rules]
Вывод:   файл:строка — [правило] что не так — как исправить
         Находок: N
Выход:   0 — находок нет, 1 — есть находки, 2 — ошибка ввода.

Каждое правило ссылается на раздел каталога knowledge/язык/антипаттерны.md.
Осознанный выбор (например, необрутализм) помечают комментарием
`aidesign-ignore: <id> — причина` на той же или предыдущей строке.
Только стандартная библиотека Python 3.9+.
"""

import argparse
import bisect
import colorsys
import json
import re
import sys
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

EXTENSIONS = {".html", ".htm", ".css"}
SKIP_DIRS = {"node_modules", ".git", ".sources", "__pycache__", ".aidesign-work", ".aispa-work"}


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    message: str
    fix: str
    ref: str


@dataclass
class Decl:
    selector: str
    prop: str
    value: str
    line: int
    block: int


# ---------- разбор файла ----------

def _blank(match: "re.Match") -> str:
    """Заменяет совпадение пробелами, сохраняя переводы строк (и номера строк)."""
    return re.sub(r"[^\n]", " ", match.group(0))


class Doc:
    """Один файл: исходник, видимый текст, CSS-объявления, строки игнора."""

    def __init__(self, path: Path, text: str):
        self.path = path
        self.text = text
        self.is_html = path.suffix.lower() in {".html", ".htm"}
        self._nl = [i for i, ch in enumerate(text) if ch == "\n"]
        self.decls: List[Decl] = []
        self._blocks = 0
        if self.is_html:
            for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S | re.I):
                self._parse_css(m.group(1), m.start(1))
            for m in re.finditer(r"\sstyle\s*=\s*\"([^\"]*)\"", text, re.I):
                self._parse_decls("[style]", m.group(1), m.start(1))
            self.scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", text, re.S | re.I))
            masked = re.sub(r"<!--.*?-->", _blank, text, flags=re.S)
            masked = re.sub(r"<(script|style)[^>]*>.*?</\1>", _blank, masked, flags=re.S | re.I)
            self.markup = masked
            self.visible = re.sub(r"<[^>]*>", _blank, masked)
        else:
            self._parse_css(text, 0)
            self.scripts = ""
            self.markup = ""
            self.visible = ""
        self.ignores = self._collect_ignores()

    def line_of(self, offset: int) -> int:
        return bisect.bisect_left(self._nl, offset) + 1

    def _parse_css(self, css: str, base: int) -> None:
        clean = re.sub(r"/\*.*?\*/", _blank, css, flags=re.S)
        for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", clean):
            selector = " ".join(m.group(1).split())
            self._parse_decls(selector, m.group(2), base + m.start(2))

    def _parse_decls(self, selector: str, body: str, base: int) -> None:
        self._blocks += 1
        pos = 0
        for part in body.split(";"):
            if ":" in part:
                prop, value = part.split(":", 1)
                lead = len(part) - len(part.lstrip())
                self.decls.append(Decl(selector, prop.strip().lower(), value.strip(),
                                       self.line_of(base + pos + lead), self._blocks))
            pos += len(part) + 1

    def _collect_ignores(self) -> dict:
        result: dict = {}
        for i, raw in enumerate(self.text.split("\n"), start=1):
            m = re.search(r"aidesign-ignore:\s*([a-z0-9,\s-]+)", raw)
            if m:
                ids = {t for t in re.split(r"[\s,]+", m.group(1)) if t and t != "-"}
                for ln in (i, i + 1):
                    result.setdefault(ln, set()).update(ids)
        return result

    def block(self, decl: Decl) -> List[Decl]:
        return [d for d in self.decls if d.block == decl.block]

    def tags(self, name: str) -> Iterable[Tuple["re.Match", int]]:
        for m in re.finditer(r"<%s\b[^>]*>" % name, self.markup, re.I):
            yield m, self.line_of(m.start())


# ---------- цвет ----------

NAMED = {"purple": "#800080", "violet": "#ee82ee", "indigo": "#4b0082", "blueviolet": "#8a2be2",
         "mediumpurple": "#9370db", "rebeccapurple": "#663399", "lavender": "#e6e6fa",
         "magenta": "#ff00ff", "fuchsia": "#ff00ff", "black": "#000000", "white": "#ffffff"}
COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(?:%s)\b" % "|".join(NAMED), re.I)


def parse_color(token: str) -> Optional[Tuple[float, float, float]]:
    """Возвращает (оттенок°, светлота 0..1, насыщенность 0..1) или None."""
    t = NAMED.get(token.lower(), token)
    rgb = None
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        if len(h) in (6, 8):
            rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    elif t.lower().startswith("rgb"):
        nums = re.findall(r"[\d.]+%?", t)[:3]
        if len(nums) == 3:
            rgb = [float(n[:-1]) / 100 if n.endswith("%") else float(n) / 255 for n in nums]
    elif t.lower().startswith("hsl"):
        nums = re.findall(r"[\d.]+", t)[:3]
        if len(nums) == 3:
            return float(nums[0]) % 360, float(nums[2]) / 100, float(nums[1]) / 100
    if rgb is None:
        return None
    hue, light, sat = colorsys.rgb_to_hls(*rgb)
    return hue * 360, light, sat


def colors_in(value: str) -> List[Tuple[float, float, float]]:
    return [c for c in (parse_color(m.group(0)) for m in COLOR_RE.finditer(value)) if c]


def chromatic(c) -> bool:
    return c[2] > 0.3 and 0.15 < c[1] < 0.9


def is_violet(c) -> bool:
    return 245 <= c[0] <= 300 and c[2] > 0.25 and 0.2 < c[1] < 0.92


def is_neon(c) -> bool:
    return c[2] > 0.8 and 0.4 < c[1] < 0.7 and (60 <= c[0] <= 200 or c[0] <= 20)


# ---------- вспомогательное ----------

TEXT_SEL = re.compile(r"(^|[\s,>+~(])(p|body|li|article|blockquote|dd|main)\b|\.(text|body|lead|prose|content|copy|description)\b")
HEADING_SEL = re.compile(r"\bh[1-6]\b|title|heading|display|hero|logo|brand", re.I)


def is_text_selector(sel: str) -> bool:
    return bool(TEXT_SEL.search(sel)) and not HEADING_SEL.search(sel)


def length(value: str) -> Optional[Tuple[float, str]]:
    m = re.match(r"\s*(-?[\d.]+)(px|em|rem|ch|%|vh|svh|dvh)?", value)
    if not m or m.group(1) in {"-", "."}:
        return None
    try:
        return float(m.group(1)), (m.group(2) or "")
    except ValueError:
        return None


def split_layers(value: str) -> List[str]:
    out, depth, cur = [], 0, ""
    for ch in value:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur]


def shadow_parts(layer: str) -> Optional[Tuple[List[float], str]]:
    if "inset" in layer:
        return None
    colorless = COLOR_RE.sub(" ", layer)
    nums = [float(n) for n in re.findall(r"(-?[\d.]+)(?:px|rem|em)?(?![\w(])", colorless)]
    return nums, layer


Hit = Tuple[int, str]  # (строка, уточнение)


def decl_hits(doc: Doc, test: Callable[[Decl], bool]) -> List[Hit]:
    return [(d.line, "") for d in doc.decls if test(d)]


def text_hits(doc: Doc, pattern: "re.Pattern", source: str = "visible") -> List[Hit]:
    text = getattr(doc, source)
    return [(doc.line_of(m.start()), m.group(0).strip()[:40]) for m in pattern.finditer(text)]


def first(hits: List[Hit]) -> List[Hit]:
    return hits[:1]


# ---------- проверки: типографика ----------

OVERUSED_FONTS = {"inter", "roboto", "geist", "space grotesk", "plus jakarta sans", "fraunces"}


def c_overused_font(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop == "font-family":
            head = d.value.split(",")[0].strip().strip("'\"").lower()
            if head in OVERUSED_FONTS:
                hits.append((d.line, head))
    for m in re.finditer(r"fonts\.googleapis\.com/css2?\?[^\"'>]*", doc.markup):
        for fam in re.findall(r"family=([^:&\"']+)", m.group(0)):
            if fam.replace("+", " ").lower() in OVERUSED_FONTS:
                hits.append((doc.line_of(m.start()), fam))
    return first(hits)


def c_caps_label(doc: Doc) -> List[Hit]:
    hits = []
    skip = re.compile(r"button|btn|nav|tab|\bth\b|badge|kbd|chip|tag|status", re.I)
    for d in doc.decls:
        if d.prop == "text-transform" and "uppercase" in d.value and not skip.search(d.selector) \
                and not is_text_selector(d.selector):
            for o in doc.block(d):
                if o.prop == "letter-spacing":
                    ln = length(o.value)
                    if ln and ((ln[1] == "em" and ln[0] >= 0.08) or (ln[1] == "px" and ln[0] >= 1)):
                        hits.append((d.line, d.selector[:40]))
    return hits


EYEBROW_CLASS = re.compile(r"class\s*=\s*\"[^\"]*\b(eyebrow|kicker|overline|pretitle|pre-title|supertitle|over-title)\b", re.I)


def c_eyebrow_class(doc: Doc) -> List[Hit]:
    return text_hits(doc, EYEBROW_CLASS, "markup")


def c_letter_spacing(doc: Doc, crushed: bool) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop != "letter-spacing":
            continue
        ln = length(d.value)
        if not ln or ln[1] not in {"em", "px"}:
            continue
        val = ln[0] if ln[1] == "em" else ln[0] / 16
        if crushed and val < -0.04:
            hits.append((d.line, d.value))
        if not crushed and val > 0.05 and is_text_selector(d.selector):
            hits.append((d.line, d.value))
    return hits


def c_caps_body(doc: Doc) -> List[Hit]:
    return decl_hits(doc, lambda d: d.prop == "text-transform" and "uppercase" in d.value
                     and is_text_selector(d.selector))


def c_tight_leading(doc: Doc) -> List[Hit]:
    def bad(d: Decl) -> bool:
        ln = length(d.value)
        return (d.prop == "line-height" and is_text_selector(d.selector) and ln is not None
                and ln[1] == "" and ln[0] < 1.3)
    return decl_hits(doc, bad)


def c_long_measure(doc: Doc) -> List[Hit]:
    def bad(d: Decl) -> bool:
        ln = length(d.value)
        return d.prop == "max-width" and is_text_selector(d.selector) and ln is not None \
            and ln[1] == "ch" and ln[0] > 80
    return decl_hits(doc, bad)


def c_justified(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop == "text-align" and d.value.startswith("justify"):
            if not any(o.prop in {"hyphens", "-webkit-hyphens"} and "auto" in o.value for o in doc.block(d)):
                hits.append((d.line, ""))
    return hits


def c_tiny_text(doc: Doc) -> List[Hit]:
    def bad(d: Decl) -> bool:
        ln = length(d.value)
        if d.prop != "font-size" or not ln or d.selector.strip() in {"html", ":root"}:
            return False
        return (ln[1] == "px" and ln[0] < 12) or (ln[1] in {"rem", "em"} and ln[0] < 0.75)
    return decl_hits(doc, bad)


def c_gradient_text(doc: Doc) -> List[Hit]:
    hits = decl_hits(doc, lambda d: d.prop in {"background-clip", "-webkit-background-clip"} and d.value.startswith("text"))
    return hits + text_hits(doc, re.compile(r"\bbg-clip-text\b"), "markup")


# ---------- проверки: цвет и поверхность ----------

def c_violet_gradient(doc: Doc) -> List[Hit]:
    hits = [(d.line, "") for d in doc.decls
            if "gradient(" in d.value and any(is_violet(c) for c in colors_in(d.value))]
    tw = re.compile(r"\b(from|via|to)-(purple|violet|indigo|fuchsia)-\d{2,3}\b")
    return first(hits + text_hits(doc, tw, "markup"))


def page_backgrounds(doc: Doc) -> List[Tuple[Decl, Tuple[float, float, float]]]:
    out = []
    for d in doc.decls:
        root = re.search(r"(^|,)\s*(html|body|:root)\s*($|,)", d.selector)
        if (root and d.prop in {"background", "background-color"}) or d.prop in {"--bg", "--background", "--color-bg"}:
            out.extend((d, c) for c in colors_in(d.value))
    return out


def c_dark_neon(doc: Doc) -> List[Hit]:
    if not any(c[1] < 0.1 for _, c in page_backgrounds(doc)):
        return []
    return first([(d.line, "") for d in doc.decls if any(is_neon(c) for c in colors_in(d.value))])


def c_cream_terracotta(doc: Doc) -> List[Hit]:
    cream = [d for d, c in page_backgrounds(doc) if 28 <= c[0] <= 58 and c[1] > 0.88 and c[2] > 0.15]
    if not cream:
        return []
    terra = [d for d in doc.decls for c in colors_in(d.value)
             if 8 <= c[0] <= 26 and 0.4 <= c[2] <= 0.85 and 0.42 <= c[1] <= 0.66]
    return first([(terra[0].line, "")]) if terra else []


def c_glow(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop not in {"box-shadow", "text-shadow"}:
            continue
        for layer in split_layers(d.value):
            parts = shadow_parts(layer)
            cols = colors_in(layer)
            if parts and len(parts[0]) >= 3 and parts[0][0] == 0 and parts[0][1] == 0 \
                    and parts[0][2] > 0 and any(chromatic(c) for c in cols):
                hits.append((d.line, ""))
                break
    return hits


def c_hard_shadow(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop != "box-shadow":
            continue
        for layer in split_layers(d.value):
            parts = shadow_parts(layer)
            if parts and len(parts[0]) >= 2:
                n = parts[0]
                blur = n[2] if len(n) >= 3 else 0
                if (abs(n[0]) >= 4 or abs(n[1]) >= 4) and blur == 0:
                    hits.append((d.line, ""))
                    break
    return hits


def c_side_stripe(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop in {"border-left", "border-right", "border-inline-start", "border-inline-end"}:
            ln = re.search(r"([\d.]+)px", d.value)
            colored = "var(" in d.value or any(chromatic(c) for c in colors_in(d.value))
            if ln and float(ln.group(1)) >= 2 and "solid" in d.value and colored:
                hits.append((d.line, ""))
    return hits + text_hits(doc, re.compile(r"\bborder-[lr]-[2-8]\b"), "markup")


def c_glass(doc: Doc) -> List[Hit]:
    hits = decl_hits(doc, lambda d: d.prop in {"backdrop-filter", "-webkit-backdrop-filter"} and "blur" in d.value)
    lines = sorted({h[0] for h in hits})
    return [(lines[1], "стекло на %d элементах" % len(lines))] if len(lines) >= 2 else []


def c_blur_blob(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        big = re.search(r"blur\(\s*([\d.]+)px", d.value)
        if d.prop == "filter" and big and float(big.group(1)) >= 40:
            hits.append((d.line, ""))
        elif "radial-gradient(" in d.value and "transparent" in d.value \
                and any(chromatic(c) and c[2] > 0.5 for c in colors_in(d.value)):
            hits.append((d.line, ""))
    return hits


def c_grid_bg(doc: Doc) -> List[Hit]:
    return decl_hits(doc, lambda d: d.prop.startswith("background") and d.value.count("linear-gradient(") >= 2
                     and "1px" in d.value and "repeating" not in d.value)


def c_stripes(doc: Doc) -> List[Hit]:
    return decl_hits(doc, lambda d: "repeating-linear-gradient(" in d.value)


# ---------- проверки: композиция ----------

def c_icon_tiles(doc: Doc) -> List[Hit]:
    pat = re.compile(r"<[a-z]+[^>]*class\s*=\s*\"[^\"]*icon[^\"]*\"[^>]*>.{0,200}?<h[2-4]\b", re.I | re.S)
    hits = text_hits(doc, pat, "markup")
    return first(hits) if len(hits) >= 3 else []


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
HEADING = re.compile(r"^h[2-6]$")
LIST_ITEMS = {"li", "tr", "dt", "dd", "option"}


class _Node:
    def __init__(self, tag: str, cls: str, line: int):
        self.tag, self.cls, self.line, self.children = tag, cls, line, []

    def signature(self) -> tuple:
        return (self.tag, self.cls, tuple(c.signature() for c in self.children))

    def has_heading(self) -> bool:
        return any(HEADING.match(c.tag) or c.has_heading() for c in self.children)


class _Tree(HTMLParser):
    """Дерево элементов разметки: тег, класс, дети. Только для сравнения структуры."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", "", 1)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        cls = " ".join(sorted((dict(attrs).get("class") or "").split()))
        node = _Node(tag, cls, self.getpos()[0])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, "", self.getpos()[0]))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break


def c_identical_cards(doc: Doc) -> List[Hit]:
    tree = _Tree()
    try:
        tree.feed(doc.markup)
        tree.close()
    except Exception:                      # битая разметка — правило молчит, остальные работают
        return []
    hits, todo = [], [tree.root]
    while todo:
        node = todo.pop()
        todo.extend(node.children)
        run: List[_Node] = []
        for child in node.children + [None]:
            if child is not None and run and child.signature() == run[0].signature():
                run.append(child)
                continue
            card = run[0] if run else None
            # Пункты списка, строки таблицы — честная форма перечня, не карточки.
            if card and len(run) >= 3 and card.tag not in LIST_ITEMS and len(card.children) >= 2 \
                    and card.has_heading():
                hits.append((card.line, "%d × <%s%s>" % (len(run), card.tag, " class=" + card.cls if card.cls else "")))
            run = [child] if child is not None else []
    return sorted(hits)


def c_numbered(doc: Doc) -> List[Hit]:
    hits = text_hits(doc, re.compile(r"(?<![\w.,:/-])0[1-9](?:\s*[./)])?(?![\w.,:/-])"))
    return first(hits) if len(hits) >= 3 else []


def c_vh_hero(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        if d.prop in {"height", "min-height"} and d.value.replace(" ", "") == "100vh":
            if not any("svh" in o.value or "dvh" in o.value for o in doc.block(d)):
                hits.append((d.line, ""))
    return hits


def c_z_index(doc: Doc) -> List[Hit]:
    return decl_hits(doc, lambda d: d.prop == "z-index" and d.value.strip().isdigit() and int(d.value) >= 1000)


# ---------- проверки: движение ----------

def c_bounce(doc: Doc) -> List[Hit]:
    hits = []
    for d in doc.decls:
        for m in re.finditer(r"cubic-bezier\(([^)]*)\)", d.value):
            nums = [float(x) for x in re.findall(r"-?[\d.]+", m.group(1))]
            if len(nums) == 4 and not (0 <= nums[1] <= 1 and 0 <= nums[3] <= 1):
                hits.append((d.line, m.group(0)))
        if re.search(r"bounce|elastic", d.value, re.I):
            hits.append((d.line, ""))
    js = re.compile(r"(bounce|elastic|back)\.(in|out|inOut)\b|easeOut(Bounce|Elastic|Back)\b")
    for m in js.finditer(doc.text):
        hits.append((doc.line_of(m.start()), m.group(0)))
    return hits


def c_transition_all(doc: Doc) -> List[Hit]:
    return decl_hits(doc, lambda d: d.prop in {"transition", "transition-property"}
                     and re.search(r"(^|,)\s*all\b", d.value) is not None)


def c_reduced_motion(doc: Doc) -> List[Hit]:
    # shared_reduced_motion ставит scan(): правило есть в соседнем CSS той же проверки.
    if "prefers-reduced-motion" in doc.text or getattr(doc, "shared_reduced_motion", False):
        return []
    motion = [d for d in doc.decls if (d.prop.startswith("animation") or d.prop.startswith("transition"))
              and not d.value.startswith("none")]
    return [(motion[0].line, "")] if motion else []


def c_anim_name(doc: Doc, words: str) -> List[Hit]:
    pat = re.compile(words, re.I)
    hits = [(d.line, "") for d in doc.decls if d.prop in {"animation", "animation-name"} and pat.search(d.value)]
    return first(hits)


def c_marquee(doc: Doc) -> List[Hit]:
    return first(c_anim_name(doc, r"marquee|ticker") + text_hits(doc, re.compile(r"<marquee\b", re.I), "markup"))


def c_pulsing(doc: Doc) -> List[Hit]:
    return first(c_anim_name(doc, r"\bpulse|\bping\b") + text_hits(doc, re.compile(r"\banimate-(pulse|ping)\b"), "markup"))


def c_hidden_at_rest(doc: Doc) -> List[Hit]:
    reveal = re.compile(r"reveal|fade|\banimate|aos|appear|in-?view|data-animate|scroll-?in", re.I)
    guard = re.compile(r"\.js\b|html\.js|\[data-js|:not\(\.no-js\)|is-visible|in-view\.|\.visible", re.I)
    return [(d.line, d.selector[:40]) for d in doc.decls
            if d.prop == "opacity" and d.value.strip() in {"0", "0.0"}
            and reveal.search(d.selector) and not guard.search(d.selector)]


def c_scroll_hijack(doc: Doc) -> List[Hit]:
    listen = re.compile(r"addEventListener\(\s*['\"](wheel|mousewheel|DOMMouseScroll|touchmove)['\"]")
    if "preventDefault" not in doc.text:
        return []
    return first([(doc.line_of(m.start()), "") for m in listen.finditer(doc.text)])


def c_video_autoplay(doc: Doc) -> List[Hit]:
    return [(ln, "") for m, ln in doc.tags("video")
            if re.search(r"\bautoplay\b", m.group(0), re.I)
            and not (re.search(r"\bmuted\b", m.group(0), re.I) and re.search(r"\bplaysinline\b", m.group(0), re.I))]


# ---------- проверки: картинки и текст ----------

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-☄☇-✒✖-➿⭐⭕]")


def c_emoji(doc: Doc) -> List[Hit]:
    seen, hits = set(), []
    for line, frag in text_hits(doc, EMOJI):
        if line not in seen:
            seen.add(line)
            hits.append((line, frag))
    return hits


def c_placeholder_image(doc: Doc) -> List[Hit]:
    bad = re.compile(r"\ssrc\s*=\s*\"(\s*|#|[^\"]*(placeholder|placehold|dummyimage|picsum)[^\"]*)\"", re.I)
    return [(ln, "") for m, ln in doc.tags("img") if bad.search(m.group(0))]


PLACEHOLDER = re.compile(r"lorem ipsum|\{\{\s*[\w.]+\s*\}\}|\[(Company Name|Your [A-Z][a-z]+|Название[^\]]*|Имя[^\]]*)\]|Certainly!", re.I)
# Видимая заглушка скилла «[ЦЕНА — впиши]» — честная метка, её требует правило 1 SKILL.md.
SKILL_PLACEHOLDER = re.compile(r"\[[^\[\]\n]{1,80}?\s[—–-]\s*впиши\s*\]", re.I)


def without_skill_placeholders(doc: Doc) -> str:
    return SKILL_PLACEHOLDER.sub(_blank, doc.visible)


def c_placeholder_text(doc: Doc) -> List[Hit]:
    text = without_skill_placeholders(doc)
    return [(doc.line_of(m.start()), m.group(0).strip()[:40]) for m in PLACEHOLDER.finditer(text)]


# Число с «+» рядом со словом-похвалой: «10,000+ happy customers», «1000+ довольных клиентов».
METRIC = re.compile(
    r"(?<![\w+.,])\d(?:[\d,.   ]*\d)?\s*(?:k|m|к|тыс\.?|млн)?\s*\+(?!\+)\s*"
    r"(?:[^\s<>]+\s+){0,2}?"
    r"(happy|satisfied|customers?|clients?|users?|teams?|companies|businesses|students?|members?|"
    r"subscribers?|downloads?|reviews?|installs?|довольн\w*|счастлив\w*|клиент\w*|пользовател\w*|"
    r"покупател\w*|компани\w*|учени\w*|студент\w*|подписчик\w*|отзыв\w*|скачиван\w*|установ\w*|"
    r"команд\w*|партн[её]р\w*)\b", re.I)


def c_invented_metrics(doc: Doc) -> List[Hit]:
    text = without_skill_placeholders(doc)
    return [(doc.line_of(m.start()), " ".join(m.group(0).split())[:40]) for m in METRIC.finditer(text)]


# Безликая кнопка-призыв: фраза — весь текст кнопки или ссылки-кнопки.
GENERIC_CTA = {
    "get started", "get started now", "start now", "learn more", "read more", "click here", "sign up",
    "sign up now", "try it now", "try now", "join now", "submit", "find out more", "discover more",
    "начать", "начать сейчас", "узнать больше", "подробнее", "узнать подробнее", "читать далее",
    "нажмите здесь", "жми", "попробовать", "попробовать сейчас", "присоединиться", "отправить",
}
BUTTONISH = re.compile(r"\b(btn|button|cta)\b", re.I)


def cta_text(inner: str) -> str:
    text = re.sub(r"<[^>]*>", " ", inner)
    text = re.sub(r"&rarr;|&nbsp;|&#8594;", " ", text)
    return " ".join(re.sub(r"[→←↗›»!.…\-–—>]+", " ", text).split()).lower()


def c_generic_cta(doc: Doc) -> List[Hit]:
    hits = []
    for m in re.finditer(r"<(button|a)\b([^>]*)>(.*?)</\1\s*>", doc.markup, re.I | re.S):
        attrs = m.group(2)
        opening = attrs + ">"
        if m.group(1).lower() == "a" and not (BUTTONISH.search(attr(opening, "class") or "")
                                              or (attr(opening, "role") or "").lower() == "button"):
            continue
        text = cta_text(m.group(3))
        if text in GENERIC_CTA:
            hits.append((doc.line_of(m.start()), text))
    for m, ln in doc.tags("input"):
        if (attr(m.group(0), "type") or "").lower() in {"submit", "button"} \
                and cta_text(attr(m.group(0), "value") or "") in GENERIC_CTA:
            hits.append((ln, cta_text(attr(m.group(0), "value"))))
    return hits

BUZZ = re.compile(
    r"революционн\w*|инновационн\w*|бесшовн\w*|передов(ой|ая|ое|ые|ых|ым|ую)\b|мирового уровня|нового поколения|"
    r"раскро\w* (ваш |свой )?потенциал|на новый уровень|непревзойдённ\w*|в современном мире|погрузитесь в|синерги\w*|"
    r"\bseamless(ly)?\b|cutting-edge|next-gen(eration)?\b|world-class|best-in-class|supercharge|\bempower\w*|"
    r"unlock the power|revolutionary|game-?chang\w*|state-of-the-art|\bunleash\w*|\beffortless(ly)?\b|\bstreamline\w*|"
    r"\bdelve\b|\btapestry\b", re.I)


def c_three_dots(doc: Doc) -> List[Hit]:
    return text_hits(doc, re.compile(r"(?<!\.)\.\.\.(?!\.)"))


def c_arrow_links(doc: Doc) -> List[Hit]:
    hits = text_hits(doc, re.compile(r"(→|->|&rarr;)\s*</(a|button)>", re.I), "markup")
    return first(hits) if len(hits) >= 3 else []


# ---------- проверки: доступность ----------

def attr(tag: str, name: str) -> Optional[str]:
    m = re.search(r"\s%s\s*=\s*\"([^\"]*)\"" % name, tag, re.I)
    if m:
        return m.group(1)
    return "" if re.search(r"\s%s(\s|>|/)" % name, tag, re.I) else None


def c_zoom(doc: Doc) -> List[Hit]:
    return [(ln, "") for m, ln in doc.tags("meta")
            if (attr(m.group(0), "name") or "").lower() == "viewport"
            and re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", m.group(0), re.I)]


def c_img_alt(doc: Doc) -> List[Hit]:
    return [(ln, "") for m, ln in doc.tags("img") if attr(m.group(0), "alt") is None]


def c_img_size(doc: Doc) -> List[Hit]:
    return [(ln, "") for m, ln in doc.tags("img")
            if (attr(m.group(0), "width") is None or attr(m.group(0), "height") is None)
            and "aspect-ratio" not in m.group(0)]


def c_click_div(doc: Doc) -> List[Hit]:
    return text_hits(doc, re.compile(r"<(div|span)\b[^>]*\sonclick\s*=", re.I), "markup")


def c_icon_button(doc: Doc) -> List[Hit]:
    hits = []
    for m in re.finditer(r"<button\b([^>]*)>(.*?)</button>", doc.markup, re.I | re.S):
        inner = re.sub(r"<[^>]*>", "", m.group(2)).strip()
        named = re.search(r"aria-label(ledby)?\s*=|\stitle\s*=", m.group(1), re.I)
        if not inner and not named:
            hits.append((doc.line_of(m.start()), ""))
    return hits


def c_input_label(doc: Doc) -> List[Hit]:
    fors = set(re.findall(r"<label\b[^>]*\sfor\s*=\s*\"([^\"]+)\"", doc.markup, re.I))
    hits = []
    for m, ln in doc.tags("input"):
        tag = m.group(0)
        if (attr(tag, "type") or "text").lower() in {"hidden", "submit", "button", "image", "reset"}:
            continue
        if attr(tag, "aria-label") is not None or attr(tag, "aria-labelledby") is not None:
            continue
        if attr(tag, "id") in fors:
            continue
        before = doc.markup[:m.start()].lower()
        if before.rfind("<label") > before.rfind("</label>"):
            continue
        hits.append((ln, ""))
    return hits


def c_outline(doc: Doc) -> List[Hit]:
    if ":focus-visible" in doc.text:
        return []
    return decl_hits(doc, lambda d: d.prop == "outline" and d.value.split()[0] in {"none", "0"})


def c_headings(doc: Doc) -> List[Hit]:
    hits, prev = [], 0
    for m in re.finditer(r"<h([1-6])\b", doc.markup, re.I):
        level = int(m.group(1))
        if prev and level > prev + 1:
            hits.append((doc.line_of(m.start()), "h%d после h%d" % (level, prev)))
        prev = level
    return hits


def c_tabindex(doc: Doc) -> List[Hit]:
    return text_hits(doc, re.compile(r"\stabindex\s*=\s*\"?[1-9]", re.I), "markup")


# ---------- реестр правил ----------

@dataclass
class Rule:
    id: str
    description: str
    ref: str
    advice: str
    check: Callable[[Doc], List[Hit]]
    html_only: bool = False


def R(rid, anchor, description, advice, check, html_only=False):
    return Rule(rid, description, "антипаттерны.md#" + anchor, advice, check, html_only)


RULES: List[Rule] = [
    # Типографика
    R("overused-font", "overused-font", "затасканный шрифт как основной", "выбрать гарнитуру под предмет (типографика.md)", c_overused_font),
    R("eyebrow-class", "eyebrow", "капс-надзаголовок над заголовком", "удалить метку, пусть говорит заголовок", c_eyebrow_class, True),
    R("caps-label", "eyebrow", "метка прописными с разрядкой", "обычный регистр или встроить смысл в заголовок", c_caps_label),
    R("crushed-tracking", "crushed-tracking", "разрядка туже −0.04em", "−0.02…−0.03em для крупного кегля", lambda d: c_letter_spacing(d, True)),
    R("wide-tracking", "wide-tracking", "разрядка в основном тексте больше 0.05em", "убрать разрядку у абзацев", lambda d: c_letter_spacing(d, False)),
    R("caps-body", "caps-body", "основной текст прописными", "обычный регистр, капс — для пары слов", c_caps_body),
    R("tight-leading", "tight-leading", "интерлиньяж текста меньше 1.3", "line-height 1.5–1.7", c_tight_leading),
    R("long-measure", "long-measure", "строка шире 80 знаков", "max-width 65–75ch", c_long_measure),
    R("justified-text", "justified", "выключка по ширине без переносов", "text-align: left или hyphens: auto", c_justified),
    R("tiny-text", "tiny-text", "текст мельче 12px", "основной от 16px, служебный от 12–13px", c_tiny_text),
    R("gradient-text", "gradient-text", "градиентный текст", "сплошной цвет, акцент — весом и размером", c_gradient_text),
    # Цвет и поверхность
    R("ai-violet-gradient", "ai-violet", "фиолетово-синий градиент", "цвет из предмета и бренда (цвет.md)", c_violet_gradient),
    R("dark-neon", "dark-neon", "почти чёрный фон с кислотным акцентом", "тему выбирать по сцене, акцент сдержанный", c_dark_neon),
    R("cream-terracotta", "cream-terracotta", "кремовый фон с терракотовым акцентом", "палитра под предмет, не «вкус по умолчанию»", c_cream_terracotta),
    R("glow-shadow", "glow", "цветное свечение вместо тени", "нейтральная тень со смещением вниз", c_glow),
    R("hard-offset-shadow", "hard-shadow", "жёсткая тень без размытия", "мягкая тень; если стиль необрутализм — aidesign-ignore", c_hard_shadow),
    R("side-stripe", "side-stripe", "цветная полоса сбоку блока", "убрать полосу, статус — иконкой или тоном фона", c_side_stripe),
    R("glass-default", "glass", "стекло (backdrop-filter) на многих элементах", "стекло в одном месте, остальное — плотные поверхности", c_glass),
    R("blur-blob", "blur-blob", "размытое цветное пятно на фоне", "ровная поверхность или фактура предмета", c_blur_blob),
    R("grid-background", "grid-background", "декоративный фон в клетку", "сетка только там, где она несёт смысл", c_grid_bg),
    R("repeating-stripes", "stripes", "полосатый фон", "ровная поверхность", c_stripes),
    # Композиция
    R("icon-tile-cards", "card-grid", "сетка карточек «иконка → заголовок → текст»", "раскладка по смыслу, иконка в строке с заголовком", c_icon_tiles, True),
    R("identical-cards", "identical-cards", "три и больше одинаковых по устройству карточки подряд", "разный вес и форма по смыслу: главное крупнее, остальное списком или таблицей", c_identical_cards, True),
    R("numbered-markers", "numbered-markers", "номера разделов 01 / 02 / 03", "номера только у настоящей последовательности", c_numbered, True),
    R("vh-hero", "vh-hero", "высота 100vh", "min-height: 100svh (запас 100vh)", c_vh_hero),
    R("z-index-chaos", "z-index-chaos", "z-index 1000 и больше", "шкала слоёв 10/20/30/50 в переменных", c_z_index),
    # Движение
    R("bounce-easing", "bounce", "пружинящая кривая (bounce/elastic/back)", "cubic-bezier(0.16, 1, 0.3, 1)", c_bounce),
    R("transition-all", "transition-all", "transition: all", "перечислить свойства: transform, opacity, color", c_transition_all),
    R("no-reduced-motion", "no-reduced-motion", "анимация без prefers-reduced-motion", "добавить @media (prefers-reduced-motion: reduce)", c_reduced_motion),
    R("pulsing-dot", "pulsing-dot", "пульсирующий индикатор", "статичная метка с подписью", c_pulsing),
    R("blinking-cursor", "blinking-cursor", "мигающий курсор «печатает»", "убрать имитацию ввода", lambda d: c_anim_name(d, r"blink|caret|typewriter")),
    R("marquee", "marquee", "бегущая строка", "статичный ряд или пауза + reduced-motion", c_marquee),
    R("hidden-at-rest", "section-fade", "контент скрыт до анимации (opacity: 0)", "видим по умолчанию, анимация только добавляет", c_hidden_at_rest),
    R("scroll-hijack", "scroll-hijack", "перехват колеса прокрутки", "родная прокрутка, сцены привязать к ней", c_scroll_hijack),
    R("video-autoplay", "video-autoplay", "автозапуск видео без muted и playsinline", "autoplay muted loop playsinline + постер", c_video_autoplay, True),
    # Картинки и текст
    R("emoji-icons", "emoji-icons", "эмодзи вместо иконок", "иконки одной библиотеки или свой SVG", c_emoji, True),
    R("placeholder-image", "placeholder-image", "картинка-заглушка или пустой src", "настоящая картинка или честная плашка", c_placeholder_image, True),
    R("placeholder-text", "placeholder-text", "текст-заглушка", "настоящий текст; нет факта — видимая метка «[… — впиши]»", c_placeholder_text, True),
    R("invented-metrics", "invented-facts", "цифра-похвала «N+ довольных клиентов»", "только цифра из брифа с источником; нет — «[Число клиентов — впиши]»", c_invented_metrics, True),
    R("generic-cta", "generic-cta", "безликая кнопка-призыв", "глагол и объект: «Записаться на субботу»", c_generic_cta, True),
    R("buzzwords", "buzzwords", "маркетинговый штамп", "конкретный глагол и предмет", lambda d: text_hits(d, BUZZ), True),
    R("three-dots", "three-dots", "три точки вместо многоточия", "символ «…»", c_three_dots, True),
    R("arrow-links", "arrow-links", "стрелка после каждой ссылки", "стрелка только у шага дальше, одна на экран", c_arrow_links, True),
    # Доступность
    R("zoom-disabled", "zoom-disabled", "запрещено масштабирование", "width=device-width, initial-scale=1", c_zoom, True),
    R("img-no-alt", "img-no-alt", "картинка без alt", "описать смысл или alt=\"\"", c_img_alt, True),
    R("img-no-size", "img-no-size", "картинка без width и height", "указать размеры или aspect-ratio", c_img_size, True),
    R("click-div", "click-div", "кликабельный div/span", "<button> для действия, <a> для перехода", c_click_div, True),
    R("icon-button-no-label", "icon-button", "кнопка-иконка без названия", "aria-label у кнопки, aria-hidden у иконки", c_icon_button, True),
    R("input-no-label", "input-no-label", "поле без подписи", "<label for> над полем", c_input_label, True),
    R("outline-none", "outline-none", "убран контур фокуса без замены", ":focus-visible с заметным кольцом", c_outline),
    R("skipped-heading", "skipped-heading", "пропущен уровень заголовка", "уровни по порядку, размер — стилем", c_headings, True),
    R("positive-tabindex", "positive-tabindex", "tabindex больше нуля", "порядок документа, tabindex 0 или -1", c_tabindex, True),
]


# ---------- обход и вывод ----------

def collect_files(paths: Iterable) -> List[Path]:
    files: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if p.is_file():
            files.append(p)
            continue
        for f in sorted(p.rglob("*")):
            rel = f.relative_to(p).parts
            if f.is_file() and f.suffix.lower() in EXTENSIONS and not SKIP_DIRS.intersection(rel):
                files.append(f)
    return files


def scan(paths: Iterable) -> List[Finding]:
    """Проверяет файлы и папки; возвращает находки, отсортированные по файлу и строке."""
    findings: List[Finding] = []
    docs = [Doc(f, f.read_text(encoding="utf-8", errors="replace")) for f in collect_files(paths)]
    # Общий CSS сайта: @media (prefers-reduced-motion) в одном .css действует на все файлы проверки.
    shared = any(not d.is_html and "prefers-reduced-motion" in d.text for d in docs)
    for doc in docs:
        f = doc.path
        doc.shared_reduced_motion = shared
        seen = set()
        for rule in RULES:
            if rule.html_only and not doc.is_html:
                continue
            for line, detail in rule.check(doc):
                ignored = doc.ignores.get(line, set())
                if (rule.id, line) in seen or rule.id in ignored or "all" in ignored:
                    continue
                seen.add((rule.id, line))
                msg = rule.description + (" (%s)" % detail if detail else "")
                findings.append(Finding(str(f), line, rule.id, msg, rule.advice, rule.ref))
    findings.sort(key=lambda x: (x.path, x.line, x.rule))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка шаблонности HTML/CSS (aidesign)")
    parser.add_argument("paths", nargs="*", help="файлы или папки")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    parser.add_argument("--rules", action="store_true", help="показать список правил")
    args = parser.parse_args(argv)
    if args.rules:
        for r in RULES:
            print("%-22s %s → %s" % (r.id, r.description, r.ref))
        return 0
    if not args.paths:
        print("Ошибка: укажите файл или папку с HTML/CSS.", file=sys.stderr)
        return 2
    try:
        files = collect_files(args.paths)
    except FileNotFoundError as err:
        print("Ошибка: нет такого пути: %s" % err, file=sys.stderr)
        return 2
    if not files:
        print("Ошибка: в указанных путях нет файлов .html, .htm или .css.", file=sys.stderr)
        return 2
    findings = scan(files)
    if args.json:
        print(json.dumps({"count": len(findings), "findings": [asdict(f) for f in findings]},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print("%s:%d — [%s] %s — %s" % (f.path, f.line, f.rule, f.message, f.fix))
        print("Находок: %d" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
