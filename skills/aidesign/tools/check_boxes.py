# По мотивам: pbakaus/impeccable (Apache-2.0) — crates/core/src/checks/{rules,measures}.rs, crates/foundation/src/rules/text.rs;
# код написан заново, пороги — из источника.
"""Правила check.py по каскаду: коробки и кегли. Дерево и значения — check_dom.py и check_cascade.py.

Вложенные карточки, тесные поля, слой под overflow: hidden, повтор текста в одной карточке,
плоская иерархия кеглей, огромный длинный h1, курсивная антиква в заголовке, мелкий текст
кнопок и ссылок.
"""

import math
import re
from typing import Dict, List, Optional, Tuple

import check_cascade as cc
import check_dom as cd

Hit = Tuple[int, str]
NOT_CARD = {"button", "input", "select", "textarea", "img", "svg", "video", "canvas", "pre", "code", "kbd",
            "label", "html", "body", "main", "dialog", "iframe", "hr", "picture", "audio", "summary"}
CONTAINERS = {"div", "section", "article", "aside", "figure", "form", "fieldset", "details", "li"}
REPEAT_SKIP = {"table", "select", "datalist", "nav", "menu", "ul", "ol"}
CONTROL_ROLES = {"dialog", "tablist", "radiogroup", "toolbar", "group", "menubar", "listbox", "switch"}
UI_TAGS = {"a", "button", "label", "th", "td", "time", "summary", "select", "input", "small", "figcaption", "dt", "dd"}


def _len(node, prop, font=16.0) -> float:
    v = cd.resolve(node, node.style.get(prop, "")).strip()
    return cd.px(v, font) or 0.0


def _edge_sides(node) -> int:
    sides = 0
    for s in cd.SIDES:
        w = _len(node, "border-%s-width" % s)
        col = cd.resolve(node, node.style.get("border-%s-color" % s, "currentColor"))
        if w > 0 and node.style.get("border-%s-style" % s, "solid") not in {"none", "hidden"} and col.strip() != "transparent":
            sides += 1
    return sides


def _shadow(node) -> bool:
    v = cd.resolve(node, node.style.get("box-shadow", "none"))
    return v.strip() not in {"none", "", "0", "unset", "initial"} and "inset" not in v


def _fill(node, bg_of) -> bool:
    raw = cd.resolve(node, node.style.get("background-color", "")).strip()
    if not raw or raw == "transparent":
        return False
    parent = node.parent
    return parent is None or bg_of(parent) != bg_of(node)


def _rounded(node) -> bool:
    v = cd.resolve(node, node.style.get("border-radius", "0"))
    return bool(re.search(r"[1-9]", v))


def c_nested_cards(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []

    def bg_of(n):
        return str(cc.background(n))

    def card(n, inner=False):
        if n.tag in NOT_CARD or n.attrs.get("role") in CONTROL_ROLES:
            return False
        edge = _edge_sides(n) >= 3 or _shadow(n)
        if inner:
            return edge and (_rounded(n) or _shadow(n))
        return (edge or _fill(n, bg_of)) and (_rounded(n) or _shadow(n))

    hits = []
    for n in root.walk():
        if n.tag == "#root" or not card(n, inner=True):
            continue
        kids = [c.tag for c in n.children]
        if kids and kids[0] in {"svg", "canvas", "pre", "video", "img", "iframe", "picture"}:
            continue                               # рамка вокруг встроенного: схема, вывод, плеер
        pill = cd.resolve(n, n.style.get("border-radius", "")).strip()
        if (re.search(r"9{3,}|50%", pill)) and len(n.all_text()) < 40:
            continue                               # таблетка-метка, а не карточка
        outer = next((a for a in n.ancestors() if a.tag in {"dialog"} or a.attrs.get("role") == "dialog" or card(a)), None)
        if outer is not None and outer.tag != "dialog" and outer.attrs.get("role") != "dialog":
            hits.append((n.line, "внутри <%s> со строки %d" % (outer.tag, outer.line)))
    return hits


def c_thin_border_row(core, doc) -> List[Hit]:
    """Ряд от трёх блоков (соседи или их обёртки до двух уровней) с рамкой до 1.5px и тенью от 32px."""
    import check_parity
    root = cc.tree(core, doc)
    if root is None:
        return []

    def visible_edge(n, col: str) -> bool:
        c, fill = cd.rgba(col), cd.rgba(cd.resolve(n, n.style.get("background-color", "")) or "transparent")
        if c is None or c[3] == 0:
            return c is None and col != "transparent"
        return not (fill and fill[3] > 0.9 and sum(abs(a - b) for a, b in zip(c[:3], fill[:3])) < 24)

    def pair(n) -> bool:
        if n.tag in NOT_CARD or cc.hidden(n):
            return False
        thin = 0
        for s in cd.SIDES:
            w = _len(n, "border-%s-width" % s)
            col = cd.resolve(n, n.style.get("border-%s-color" % s, "currentColor")).strip()
            thin += 0 < w <= 1.5 and n.style.get("border-%s-style" % s, "solid") not in {"none", "hidden"} \
                and visible_edge(n, col)
        return thin >= 2 and check_parity.shadow_blur(core, cd.resolve(n, n.style.get("box-shadow", "none"))) >= 32

    def within(cell, depth=0):
        if pair(cell):
            return cell, depth
        if depth == 2:
            return None
        return next((x for x in (within(c, depth + 1) for c in cell.children) if x is not None), None)

    hits, seen = [], set()
    for parent in root.walk():
        groups: Dict[tuple, list] = {}
        for c in parent.children:
            found = within(c)
            if found:                              # ряд — ячейки одного вида, карточка на одной глубине
                groups.setdefault((c.tag, found[1]), []).append(found[0])
        for row in groups.values():
            if len(row) >= 3 and row[0].offset not in seen:
                seen.update(x.offset for x in row)
                hits.append((row[0].line, "%d блока подряд" % len(row)))
    return hits


def c_cramped(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    hits = []
    for n in root.walk():
        if n.tag in {"#root", "input", "select", "textarea", "code", "kbd", "mark", "html", "body"} \
                or len(n.text.strip()) < 2 or cd.inherited(n, "display")[0] == "none":
            continue
        fill = _fill(n, lambda x: str(cc.background(x)))
        inline = n.tag in {"a", "span", "strong", "em", "b", "i", "small", "abbr"} \
            and n.style.get("display", "") not in {"inline-block", "block", "flex", "inline-flex", "grid"}
        box = _edge_sides(n) >= 3 or (fill and not inline)
        if not box:
            continue
        font = cd.font_px(n, "min")
        default = 6.0 if n.tag == "button" else 0.0
        side = []
        for s in ("left", "right"):
            raw = cd.resolve(n, n.style.get("padding-" + s, "")).strip()
            side.append(cd.px(raw, font) if raw else default)
        if None in side:
            continue                               # clamp(), %, calc() — статикой не измерить
        h = min(side)
        if h < max(4.0, 0.25 * font):
            hits.append((n.line, "поле %gpx при кегле %gpx, %s" % (round(h, 1), round(font, 1), "<%s>" % n.tag)))
    return hits


def c_clipped(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    hits = []
    for n in root.walk():
        ox, oy = n.style.get("overflow-x", ""), n.style.get("overflow-y", "")
        clip_x, clip_y = ox in {"hidden", "clip"}, oy in {"hidden", "clip"}
        if not (clip_x or clip_y) or re.search(r"\b(sr-only|visually-hidden)\b", " ".join(n.classes)):
            continue
        for c in [c for k in n.children for c in [k] + k.children]:
            if c.style.get("position") != "absolute":
                continue
            for prop, axis in (("top", clip_y), ("bottom", clip_y), ("left", clip_x), ("right", clip_x)):
                v = cd.resolve(c, c.style.get(prop, "")).strip()
                if axis and (re.match(r"-\s*\d*\.?\d", v) or re.fullmatch(r"100(\.0+)?%", v)):
                    hits.append((n.line, "<%s> выходит за край на строке %d" % (c.tag, c.line)))
                    break
            else:
                continue
            break
    return hits


def _sig(n) -> tuple:
    return (n.tag, tuple(sorted(n.classes)))


def c_repeated_text(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    hits, reported = [], set()

    def visit(n) -> Dict[str, List]:
        found: Dict[str, List] = {}
        for c in n.children:
            for k, v in visit(c).items():
                found.setdefault(k, []).extend(v)
        txt = " ".join(n.text.split())
        if 2 <= len(txt) <= 60 and re.search(r"[^\W\d_]", txt) and "впиши" not in txt:
            found.setdefault(txt.lower(), []).append(n)
        if n.tag in REPEAT_SKIP or n.attrs.get("role") in {"navigation", "menu", "menubar", "listbox", "grid", "tablist", "radiogroup"}:
            return {}
        if n.tag in CONTAINERS and len(n.all_text()) <= 600:
            for k, nodes in found.items():
                if len(nodes) >= 3 and len({_sig(x) for x in nodes}) >= 2 and k not in reported:
                    reported.add(k)
                    hits.append((n.line, "«%s» ×%d" % (nodes[0].text.strip()[:30], len(nodes))))
        return found

    visit(root)
    return hits


def _role(n) -> Optional[str]:
    if re.fullmatch(r"h[1-6]", n.tag):
        return n.tag
    return "body" if n.tag in {"p", "li"} else None


def c_flat_hierarchy(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    sizes: Dict[str, List[float]] = {}
    authored = False
    first = None
    for n in root.walk():
        role = _role(n)
        if not role or not n.all_text().strip():
            continue
        sizes.setdefault(role, []).append(round(cd.font_px(n, "max"), 1))
        if role != "body":
            first = first or n
            authored = authored or any("font-size" in a.style for a in [n] + list(n.ancestors()) if a.tag != "html")
    ladder = {}
    for role, vals in sizes.items():
        top = max(set(vals), key=vals.count)
        if vals.count(top) * 2 >= len(vals):
            ladder[role] = top
    if len(ladder) < 3 or not authored or ("h1" in ladder and "body" in ladder and ladder["h1"] < ladder["body"]):
        return []
    steps = sorted(ladder.values())
    largest = max(b / a for a, b in zip(steps, steps[1:]) if a > 0)
    if largest >= 1.25:
        return []
    return [(first.line, "/".join("%g" % s for s in steps) + "px, шаг не больше ×%.2f" % largest)]


def c_oversized_h1(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    hits = []
    for n in root.walk():
        if n.tag != "h1":
            continue
        text = " ".join(n.all_text().split())
        size = cd.font_px(n, "max")
        if size < 72 or len(text) < 40:
            continue
        width = 1184.0
        for a in [n] + list(n.ancestors()):
            mw = cd.px(cd.resolve(a, a.style.get("max-width", "")), size)
            if mw:
                width = min(width, mw if not a.style.get("max-width", "").strip().endswith("ch") else mw)
        lh = cd.px(cd.inherited(n, "line-height")[0] or "1.1") or 1.1
        lh = lh if lh < 4 else lh / size
        lines = math.ceil(len(text) * 0.55 * size / width)
        share = lines * size * lh / 800
        if share >= 0.28:
            hits.append((n.line, "%gpx, %d знаков, ~%d%% экрана" % (round(size), len(text), share * 100)))
    return hits


def c_italic_serif(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    hits = []
    for n in root.walk():
        if n.tag not in {"h1", "h2"}:
            continue
        size = cd.font_px(n, "max")
        if size < 48 or "italic" not in cd.inherited(n, "font-style")[0]:
            continue
        fam = cd.inherited(n, "font-family")[0]
        head = fam.split(",")[0].strip().strip("'\"").lower() if fam else ""
        if head in cc.SERIFS:
            hits.append((n.line, "%s %gpx" % (head, round(size))))
    return hits


def c_undersized_ui(core, doc) -> List[Hit]:
    root = cc.tree(core, doc)
    if root is None:
        return []
    hits = []
    for n in root.walk():
        ui = n.tag in UI_TAGS or n.attrs.get("role") in {"button", "link", "tab", "menuitem"}
        if not ui or not re.search(r"[^\W\d_]", n.text) or cc.hidden(n) or n.tag in {"sup", "sub"}:
            continue
        size = cd.font_px(n, "min")
        if size < 11:
            hits.append((n.line, "%gpx у <%s>" % (round(size, 1), n.tag)))
    return hits
