"""Дерево разметки и статический каскад для check.py: что у элемента в итоге в покое.

Селекторы: тег, .класс, #id, [атрибут], :root, потомок и `>`; правила с состояниями
(:hover, ::before и т. п.) и соседями (+, ~) пропускаются — это не вид в покое. Порядок —
специфичность, затем порядок в файле; style="" и классы Tailwind — свои у элемента.
Наследуются color, font-*, line-height, visibility и переменные --*. var() раскрывается.
Подключённые <link rel="stylesheet"> с диска тоже читаются. Только стандартная библиотека.
"""

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
INHERITED = {"color", "font-size", "font-family", "font-style", "font-weight", "line-height", "visibility",
             "text-transform", "letter-spacing", "-webkit-text-fill-color"}
STATEFUL = re.compile(r":(?!root\b)[\w-]|\\|\+|~")
UA_SIZE = {"h1": 2.0, "h2": 1.5, "h3": 1.17, "h4": 1.0, "h5": 0.83, "h6": 0.67, "small": 0.83}
UA_BOLD = {"h1", "h2", "h3", "h4", "h5", "h6", "b", "strong", "th"}
CONTROLS = {"button", "input", "select", "textarea"}
KEYWORD_SIZE = {"xx-small": 9, "x-small": 10, "small": 13, "medium": 16, "large": 18, "x-large": 24,
                "xx-large": 32, "xxx-large": 48}


class Node:
    def __init__(self, tag, attrs, offset, line, parent):
        self.tag, self.attrs, self.offset, self.line, self.parent = tag, attrs, offset, line, parent
        self.classes = set((attrs.get("class") or "").split())
        self.id = attrs.get("id") or ""
        self.children: List["Node"] = []
        self.text = ""                     # свой текст (без детей)
        self.style: Dict[str, str] = {}    # итог каскада (собственные значения)
        self.origin: Dict[str, str] = {}   # откуда значение: "tw" — класс Tailwind

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def ancestors(self):
        n = self.parent
        while n is not None and n.tag != "#root":
            yield n
            n = n.parent

    def all_text(self) -> str:
        return " ".join(" ".join(n.text.split()) for n in self.walk() if n.text.strip())


class _Builder(HTMLParser):
    def __init__(self, line_starts):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, 0, 1, None)
        self.stack = [self.root]
        self.starts = line_starts

    def _offset(self):
        line, col = self.getpos()
        return self.starts[line - 1] + col, line

    def handle_starttag(self, tag, attrs):
        off, line = self._offset()
        node = Node(tag, {k: (v or "") for k, v in attrs}, off, line, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        off, line = self._offset()
        self.stack[-1].children.append(Node(tag, {k: (v or "") for k, v in attrs}, off, line, self.stack[-1]))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if data.strip():
            self.stack[-1].text += " " + data


# ---------- селекторы ----------

COMPOUND = re.compile(r"^(\*|[a-zA-Z][\w-]*)?((?:\.[\w-]+|#[\w-]+|\[[^\]]+\]|:root)*)$")


def parse_selector(sel: str):
    """Сложный селектор → [(комбинатор, (тег, классы, id, атрибуты, root))] или None."""
    if STATEFUL.search(sel.replace(":root", "")) or "@" in sel or "&" in sel:
        return None
    tokens = re.split(r"\s*(>)\s*|\s+", sel.strip())
    parts, comb = [], " "
    for t in tokens:
        if t is None or t == "":
            continue
        if t == ">":
            comb = ">"
            continue
        m = COMPOUND.match(t)
        if not m:
            return None
        rest = m.group(2)
        comp = ((m.group(1) or "*").lower(), set(re.findall(r"\.([\w-]+)", rest)),
                (re.findall(r"#([\w-]+)", rest) or [""])[0], re.findall(r"\[([^\]]+)\]", rest), ":root" in rest)
        parts.append((comb, comp))
        comb = " "
    return parts or None


def specificity(parts) -> Tuple[int, int, int]:
    a = sum(1 for _, c in parts if c[2])
    b = sum(len(c[1]) + len(c[3]) + (1 if c[4] else 0) for _, c in parts)
    return a, b, sum(1 for _, c in parts if c[0] != "*")


def _attr_ok(node: Node, expr: str) -> bool:
    m = re.match(r"\s*([\w-]+)\s*(?:([~|^$*]?=)\s*[\"']?([^\"'\]]*)[\"']?)?\s*$", expr)
    if not m or m.group(1) not in node.attrs:
        return False
    if not m.group(2):
        return True
    have, want, op = node.attrs[m.group(1)], m.group(3), m.group(2)
    return {"=": have == want, "~=": want in have.split(), "^=": have.startswith(want),
            "$=": have.endswith(want), "*=": want in have, "|=": have.split("-")[0] == want}[op]


def _compound_ok(node: Node, comp) -> bool:
    tag, classes, ident, attrs, root = comp
    if root and node.tag != "html":
        return False
    return (tag == "*" or node.tag == tag) and classes <= node.classes and (not ident or node.id == ident) \
        and all(_attr_ok(node, a) for a in attrs)


def matches(node: Node, parts) -> bool:
    if not _compound_ok(node, parts[-1][1]):
        return False
    cur, i = node, len(parts) - 2
    comb = parts[-1][0]
    while i >= 0:
        comp = parts[i][1]
        if comb == ">":
            cur = cur.parent
            if cur is None or cur.tag == "#root" or not _compound_ok(cur, comp):
                return False
        else:
            cur = cur.parent
            while cur is not None and cur.tag != "#root" and not _compound_ok(cur, comp):
                cur = cur.parent
            if cur is None or cur.tag == "#root":
                return False
        comb = parts[i][0]
        i -= 1
    return True


# ---------- каскад ----------

def _box(value: str) -> List[str]:
    v = value.split()
    if not v:
        return []
    v = (v + v[:1] * 4)[:4] if len(v) == 1 else v
    if len(v) == 2:
        v = [v[0], v[1], v[0], v[1]]
    elif len(v) == 3:
        v = [v[0], v[1], v[2], v[1]]
    return v[:4]


SIDES = ("top", "right", "bottom", "left")
WIDTH_WORD = {"thin": "1px", "medium": "3px", "thick": "5px"}


def expand(prop: str, value: str) -> List[Tuple[str, str]]:
    """Сокращения → полные свойства, которые нужны правилам."""
    v = re.sub(r"\s*!important\s*$", "", value).strip()
    if prop in {"padding", "margin"}:
        return [("%s-%s" % (prop, s), x) for s, x in zip(SIDES, _box(v))]
    if prop in {"padding-inline", "margin-inline"}:
        b = (v.split() + v.split())[:2]
        return [(prop.split("-")[0] + "-left", b[0]), (prop.split("-")[0] + "-right", b[1])]
    if prop in {"padding-block", "margin-block"}:
        b = (v.split() + v.split())[:2]
        return [(prop.split("-")[0] + "-top", b[0]), (prop.split("-")[0] + "-bottom", b[1])]
    if prop == "background":
        if re.search(r"url\(|gradient\(", v):
            return [("background-color", _last_color(v) or "transparent"), ("background-image", v)]
        return [("background-color", v), ("background-image", "none")]
    if prop in {"border", "outline"} or re.fullmatch(r"border-(top|right|bottom|left|inline-start|inline-end)", prop):
        side = {"border-inline-start": "left", "border-inline-end": "right"}.get(prop, prop[7:] if prop.startswith("border-") else "")
        sides = [side] if side else (SIDES if prop == "border" else [])
        if not sides:
            return [(prop, v)]
        width = next((WIDTH_WORD.get(t, t) for t in v.split() if re.match(r"^[\d.]+(px|rem|em)?$|^(thin|medium|thick)$", t)), "3px")
        style = next((t for t in v.split() if t in {"solid", "dashed", "dotted", "double", "none", "hidden", "groove", "ridge", "inset", "outset"}), "none")
        color = _last_color(v) or "currentColor"
        out = []
        for s in sides:
            out += [("border-%s-width" % s, width if style not in {"none", "hidden"} else "0"),
                    ("border-%s-style" % s, style), ("border-%s-color" % s, color)]
        return out
    if prop in {"border-width", "border-color", "border-style"}:
        kind = prop.split("-")[1]
        return [("border-%s-%s" % (s, kind), WIDTH_WORD.get(x, x)) for s, x in zip(SIDES, _box(v))]
    if prop == "font":
        m = re.search(r"([\d.]+(?:px|rem|em|%))(?:\s*/\s*[\d.]+\w*)?\s+(.+)$", v)
        out = [("font-style", "italic")] if re.search(r"\bitalic\b", v) else []
        if re.search(r"\bbold\b|\b[6-9]00\b", v):
            out.append(("font-weight", "700"))
        return out + ([("font-size", m.group(1)), ("font-family", m.group(2))] if m else [])
    if prop == "overflow":
        return [("overflow-x", v.split()[0]), ("overflow-y", v.split()[-1])]
    if prop == "inset":
        return [(s, x) for s, x in zip(SIDES, _box(v))]
    return [(prop, v)]


def _last_color(v: str) -> Optional[str]:
    cols = re.findall(r"#[0-9a-fA-F]{3,8}\b|(?:rgba?|hsla?)\([^)]*\)|tw\([\w-]+\)|var\([^)]*\)|\b(?:white|black|transparent)\b", v)
    if re.search(r"gradient\(|url\(", v):
        return None
    return cols[-1] if cols else None


def build(doc, sheets=()) -> Node:
    """Дерево разметки документа с итогом каскада в node.style; sheets — объявления <link>-файлов."""
    starts, acc = [], 0
    for line in doc.markup.split("\n"):
        starts.append(acc)
        acc += len(line) + 1
    b = _Builder(starts)
    try:
        b.feed(doc.markup)
        b.close()
    except Exception:                       # битая разметка — работаем с тем, что разобралось
        pass
    root = b.root
    by_owner: Dict[int, List] = {}
    rules = []
    order = 0
    groups: Dict[Tuple[int, int], List] = {}
    for src, decls in enumerate(list(sheets) + [doc.decls]):
        for d in decls:
            if d.owner >= 0:
                by_owner.setdefault(d.owner, []).append(d)
            elif d.at and not re.match(r"@(layer|supports)\b", d.at):
                continue                    # @media, @keyframes и прочие условия — не вид по умолчанию
            else:
                groups.setdefault((src, d.block), []).append(d)
    for key in sorted(groups):
        ds = groups[key]
        sel = ds[0].selector
        for one in sel.split(","):
            parts = parse_selector(one)
            if parts:
                order += 1
                rules.append((specificity(parts), order, parts, ds))
    index: Dict[str, List] = {}
    for r in rules:
        comp = r[2][-1][1]
        key = ("#" + comp[2]) if comp[2] else ("." + sorted(comp[1])[0]) if comp[1] else comp[0]
        index.setdefault(key, []).append(r)
    for node in root.walk():
        if node.tag == "#root":
            continue
        keys = [node.tag, "*"] + ["." + c for c in node.classes] + (["#" + node.id] if node.id else [])
        matched = [r for k in keys for r in index.get(k, ()) if matches(node, r[2])]
        matched.sort(key=lambda r: (r[0], r[1]))
        decls = [(d, False) for r in matched for d in r[3]] + [(d, True) for d in by_owner.get(node.offset, ())]
        normal = [x for x in decls if "!important" not in x[0].value]
        important = [x for x in decls if "!important" in x[0].value]
        for d, own in normal + important:
            for p, v in expand(d.prop, d.value):
                node.style[p] = v
                node.origin[p] = d.origin
    return root


# ---------- значения ----------

NAMED_RGB = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "gray": (128, 128, 128),
             "grey": (128, 128, 128), "silver": (192, 192, 192), "navy": (0, 0, 128), "blue": (0, 0, 255),
             "green": (0, 128, 0), "yellow": (255, 255, 0), "orange": (255, 165, 0), "purple": (128, 0, 128),
             "teal": (0, 128, 128), "maroon": (128, 0, 0), "olive": (128, 128, 0), "lightgray": (211, 211, 211),
             "lightgrey": (211, 211, 211), "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169),
             "gainsboro": (220, 220, 220), "whitesmoke": (245, 245, 245), "dimgray": (105, 105, 105)}


def rgba(value: str) -> Optional[Tuple[float, float, float, float]]:
    """Цвет CSS → (r, g, b 0..255, a 0..1); неизвестное (oklch, tw(), currentColor) → None."""
    t = value.strip().lower()
    if t == "transparent":
        return (0, 0, 0, 0.0)
    if t in NAMED_RGB:
        return NAMED_RGB[t] + (1.0,)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", t)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return None
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    m = re.fullmatch(r"rgba?\(([^)]*)\)", t)
    if m:
        nums = re.findall(r"-?[\d.]+%?", m.group(1))
        if len(nums) < 3:
            return None
        ch = [float(n[:-1]) * 2.55 if n.endswith("%") else float(n) for n in nums[:3]]
        a = nums[3] if len(nums) > 3 else "1"
        return (ch[0], ch[1], ch[2], float(a[:-1]) / 100 if a.endswith("%") else float(a))
    m = re.fullmatch(r"hsla?\(([^)]*)\)", t)
    if m:
        import colorsys
        nums = re.findall(r"-?[\d.]+%?", m.group(1))
        if len(nums) < 3:
            return None
        h, s, l_ = float(nums[0].rstrip("%")) / 360, float(nums[1].rstrip("%")) / 100, float(nums[2].rstrip("%")) / 100
        r, g, b_ = colorsys.hls_to_rgb(h % 1, l_, s)
        a = nums[3] if len(nums) > 3 else "1"
        return (r * 255, g * 255, b_ * 255, float(a[:-1]) / 100 if a.endswith("%") else float(a))
    return None


def resolve(node: Node, value: str, depth: int = 0) -> str:
    """var(--x, запас) по переменным элемента и предков."""
    if "var(" not in value or depth > 6:
        return value

    def one(m):
        name, fallback = m.group(1), (m.group(2) or "").lstrip(",").strip()
        cur = node
        while cur is not None and cur.tag != "#root":
            if name in cur.style:
                return resolve(cur, cur.style[name], depth + 1)
            cur = cur.parent
        return resolve(node, fallback, depth + 1)
    return re.sub(r"var\(\s*(--[\w-]+)\s*(,[^()]*(?:\([^()]*\)[^()]*)*)?\)", one, value)


def inherited(node: Node, prop: str) -> Tuple[str, str]:
    """(значение, origin) с учётом наследования; '' если не задано нигде."""
    cur = node
    while cur is not None and cur.tag != "#root":
        if prop in cur.style and cur.style[prop] not in {"inherit", "unset"}:
            return resolve(cur, cur.style[prop]), cur.origin.get(prop, "")
        if prop not in INHERITED:
            return "", ""
        cur = cur.parent
    return "", ""


def font_px(node: Node, which: str = "max") -> float:
    """Размер шрифта в px; clamp() — min или max (телефон / компьютер), vw — 390 / 1280."""
    chain = [node] + list(node.ancestors())
    size = 16.0
    for n in reversed(chain):
        raw = resolve(n, n.style.get("font-size", "")).strip()
        if not raw:
            if n.tag in UA_SIZE:
                size *= UA_SIZE[n.tag]
            elif n.tag in CONTROLS:
                size = 13.33
            continue
        size = _size(raw, size, which)
    return size


def _size(raw: str, parent: float, which: str) -> float:
    m = re.fullmatch(r"clamp\((.+)\)", raw)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) == 3:
            return _size(parts[2] if which == "max" else parts[0], parent, which)
    m = re.fullmatch(r"(-?[\d.]+)(px|rem|em|%|vw|pt)?", raw)
    if m:
        n, unit = float(m.group(1)), m.group(2) or "px"
        return {"px": n, "rem": n * 16, "em": n * parent, "%": n * parent / 100, "pt": n * 4 / 3,
                "vw": n * (12.8 if which == "max" else 3.9)}[unit]
    if raw in KEYWORD_SIZE:
        return KEYWORD_SIZE[raw]
    return {"smaller": parent * 0.83, "larger": parent * 1.2}.get(raw, parent)


def px(value: str, font: float = 16.0) -> Optional[float]:
    m = re.match(r"\s*(-?[\d.]+)(px|rem|em|%)?\s*$", value or "")
    if not m or m.group(1) in {"-", "."}:
        return None
    n, unit = float(m.group(1)), m.group(2)
    if unit == "%":
        return None
    return n * 16 if unit == "rem" else n * font if unit == "em" else n
