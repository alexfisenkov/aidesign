"""Классы Tailwind → CSS-объявления для правил check.py (часть проверки шаблонности).

Только то, что нужно правилам: размеры текста, цвета, рамки, скругления, тени, отступы,
интерлиньяж, разрядка, регистр, курсив, движение, высота экрана, слои. Цвета палитры
Tailwind не переводятся в точные значения (палитры в скилле нет): значение — метка
`tw(<семейство>-<оттенок>)`, по ней правила понимают «серый» и «цветной», а контраст по
таким классам не считают. Произвольные значения (`text-[#777]`, `p-[3px]`) — как есть.
Классы с вариантом (`hover:`, `md:`, `dark:`) не берутся: это не вид «в покое».
"""

import re
from typing import List, Optional, Tuple

GRAYS = {"slate", "gray", "zinc", "neutral", "stone"}
HUES = {"red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal", "cyan", "sky",
        "blue", "indigo", "violet", "purple", "fuchsia", "pink", "rose"} | GRAYS
SHADES = {"50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"}
TEXT_SIZES = {"xs": 12, "sm": 14, "base": 16, "lg": 18, "xl": 20, "2xl": 24, "3xl": 30, "4xl": 36,
              "5xl": 48, "6xl": 60, "7xl": 72, "8xl": 96, "9xl": 128}
RADII = {"none": "0", "sm": "2px", "": "4px", "md": "6px", "lg": "8px", "xl": "12px", "2xl": "16px",
         "3xl": "24px", "full": "9999px"}
SHADOWS = {"sm": "0 1px 2px 0 rgba(0,0,0,0.05)", "": "0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)",
           "md": "0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)",
           "lg": "0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)",
           "xl": "0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1)",
           "2xl": "0 25px 50px -12px rgba(0,0,0,0.25)", "none": "none"}
LEADING = {"none": "1", "tight": "1.25", "snug": "1.375", "normal": "1.5", "relaxed": "1.625", "loose": "2"}
TRACKING = {"tighter": "-0.05em", "tight": "-0.025em", "normal": "0em", "wide": "0.025em",
            "wider": "0.05em", "widest": "0.1em"}
WEIGHTS = {"thin": "100", "extralight": "200", "light": "300", "normal": "400", "medium": "500",
           "semibold": "600", "bold": "700", "extrabold": "800", "black": "900"}
SPACE_PROPS = {"p": ["padding"], "px": ["padding-left", "padding-right"], "py": ["padding-top", "padding-bottom"],
               "pt": ["padding-top"], "pr": ["padding-right"], "pb": ["padding-bottom"], "pl": ["padding-left"],
               "ps": ["padding-left"], "pe": ["padding-right"],
               "m": ["margin"], "mx": ["margin-left", "margin-right"], "my": ["margin-top", "margin-bottom"],
               "mt": ["margin-top"], "mr": ["margin-right"], "mb": ["margin-bottom"], "ml": ["margin-left"],
               "gap": ["gap"], "gap-x": ["column-gap"], "gap-y": ["row-gap"]}
SIDES = {"l": "left", "r": "right", "t": "top", "b": "bottom", "s": "left", "e": "right"}
ANIMATIONS = {"bounce": "bounce 1s infinite", "pulse": "pulse 2s cubic-bezier(0.4,0,0.6,1) infinite",
              "ping": "ping 1s cubic-bezier(0,0,0.2,1) infinite", "spin": "spin 1s linear infinite"}
SIMPLE = {
    "uppercase": ("text-transform", "uppercase"), "italic": ("font-style", "italic"),
    "text-justify": ("text-align", "justify"), "font-serif": ("font-family", "ui-serif, Georgia, serif"),
    "font-mono": ("font-family", "ui-monospace, monospace"), "h-screen": ("height", "100vh"),
    "min-h-screen": ("min-height", "100vh"), "transition-all": ("transition", "all 150ms ease"),
    "transition": ("transition", "color, background-color, border-color, opacity, transform 150ms"),
    "bg-clip-text": ("background-clip", "text"), "overflow-hidden": ("overflow", "hidden"),
    "overflow-clip": ("overflow", "clip"), "absolute": ("position", "absolute"), "fixed": ("position", "fixed"),
    "relative": ("position", "relative"), "top-full": ("top", "100%"), "left-full": ("left", "100%"),
    "border": ("border-width", "1px"), "ring-1": ("border-width", "1px"), "ring": ("border-width", "3px"),
    "backdrop-blur": ("backdrop-filter", "blur(8px)"), "hidden": ("display", "none"),
    "sr-only": ("position", "absolute"),
}
GRADIENT_DIR = re.compile(r"^bg-(?:gradient|linear)-to-(t|tr|r|br|b|bl|l|tl)$")
NUM = r"(\d+(?:\.\d+)?)"


def palette(name: str) -> Optional[str]:
    """`gray-400` → `tw(gray-400)`; `white`, `black`, `transparent`, `[#abc]` — настоящий цвет."""
    base, _, alpha = name.partition("/")
    if base in {"white", "black"}:
        rgb = "255,255,255" if base == "white" else "0,0,0"
        return "rgba(%s,%s)" % (rgb, int(alpha) / 100) if alpha.isdigit() else ("#ffffff" if base == "white" else "#000000")
    if base in {"transparent", "current", "inherit"}:
        return {"transparent": "transparent", "current": "currentColor", "inherit": "inherit"}[base]
    m = re.fullmatch(r"\[(#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?)\([^\]]*\))\]", base)
    if m:
        return m.group(1).replace("_", " ")
    fam, _, shade = base.rpartition("-")
    if fam in HUES and shade in SHADES:
        return "tw(%s-%s)" % (fam, shade)
    return None


def length(token: str, scale: float = 4.0) -> Optional[str]:
    if token == "px":
        return "1px"
    if re.fullmatch(NUM, token):
        return "%gpx" % (float(token) * scale)
    m = re.fullmatch(r"\[(-?\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw|ch))\]", token)
    return m.group(1) if m else None


def one(cls: str) -> List[Tuple[str, str]]:
    neg = cls.startswith("-")
    c = cls[1:] if neg else cls
    if c in SIMPLE:
        return [SIMPLE[c]]
    m = re.fullmatch(r"text-(xs|sm|base|lg|xl|[2-9]xl)", c)
    if m:
        return [("font-size", "%dpx" % TEXT_SIZES[m.group(1)])]
    m = re.fullmatch(r"text-\[(\d+(?:\.\d+)?(?:px|rem|em))\]", c)
    if m:
        return [("font-size", m.group(1))]
    for prefix, prop in (("text-", "color"), ("bg-", "background-color"), ("border-", "border-color")):
        if c.startswith(prefix):
            col = palette(c[len(prefix):])
            if col:
                return [(prop, col)]
    for prefix, prop in (("from-", "--tw-from"), ("via-", "--tw-via"), ("to-", "--tw-to")):
        if c.startswith(prefix) and palette(c[len(prefix):]):
            return [(prop, palette(c[len(prefix):]))]
    if GRADIENT_DIR.match(c):
        return [("background-image", "linear-gradient(var(--tw-from), var(--tw-to))")]
    m = re.fullmatch(r"rounded(?:-(none|sm|md|lg|xl|2xl|3xl|full))?", c)
    if m:
        return [("border-radius", RADII[m.group(1) or ""])]
    m = re.fullmatch(r"shadow(?:-(sm|md|lg|xl|2xl|none))?", c)
    if m:
        return [("box-shadow", SHADOWS[m.group(1) or ""])]
    m = re.fullmatch(r"border-([lrtbse])(?:-(\d+|\[\d+px\]))?", c)
    if m:
        w = (m.group(2) or "1").strip("[]px")
        return [("border-%s-width" % SIDES[m.group(1)], "%spx" % w)]
    m = re.fullmatch(r"border-(\d+)", c)
    if m:
        return [("border-width", "%spx" % m.group(1))]
    m = re.fullmatch(r"leading-(none|tight|snug|normal|relaxed|loose|\d+)", c)
    if m:
        v = m.group(1)
        return [("line-height", LEADING[v] if v in LEADING else "%gpx" % (int(v) * 4))]
    m = re.fullmatch(r"tracking-(tighter|tight|normal|wide|wider|widest|\[-?[\d.]+em\])", c)
    if m:
        v = m.group(1)
        return [("letter-spacing", TRACKING.get(v, v.strip("[]")))]
    m = re.fullmatch(r"font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)", c)
    if m:
        return [("font-weight", WEIGHTS[m.group(1)])]
    m = re.fullmatch(r"animate-(bounce|pulse|ping|spin)", c)
    if m:
        return [("animation", ANIMATIONS[m.group(1)])]
    m = re.fullmatch(r"z-(\d+|\[\d+\])", c)
    if m:
        return [("z-index", m.group(1).strip("[]"))]
    m = re.fullmatch(r"opacity-(\d+)", c)
    if m:
        return [("opacity", "%g" % (int(m.group(1)) / 100))]
    m = re.fullmatch(r"blur-(sm|md|lg|xl|2xl|3xl)", c)
    if m:
        return [("filter", "blur(%dpx)" % {"sm": 4, "md": 12, "lg": 16, "xl": 24, "2xl": 40, "3xl": 64}[m.group(1)])]
    m = re.fullmatch(r"(top|right|bottom|left|inset)-(\d+(?:\.\d+)?|px|\[[^\]]+\])", c)
    if m:
        v = length(m.group(2))
        if v:
            return [(m.group(1), ("-" + v) if neg else v)]
    m = re.fullmatch(r"(p|px|py|pt|pr|pb|pl|ps|pe|m|mx|my|mt|mr|mb|ml|gap|gap-x|gap-y)-(.+)", c)
    if m:
        v = length(m.group(2))
        if v:
            return [(p, ("-" + v) if neg else v) for p in SPACE_PROPS[m.group(1)]]
    return []


def decls_for(classes: List[str]) -> List[Tuple[str, str]]:
    """Объявления по списку классов одного элемента; варианты и неизвестное пропускаются."""
    out: List[Tuple[str, str]] = []
    for cls in classes:
        cls = cls.lstrip("!")
        if ":" in cls.split("[")[0]:
            continue
        out.extend(one(cls))
    color = next((v for p, v in out if p == "border-color"), None)
    for p, v in list(out):
        side = re.fullmatch(r"border-(left|right|top|bottom)-width", p)
        if side:                         # border-l-4 border-blue-500 → border-left: 4px solid …
            out.append(("border-" + side.group(1), "%s solid %s" % (v, color or "currentColor")))
    if any(p == "background-image" for p, _ in out):
        frm = next((v for p, v in out if p == "--tw-from"), "transparent")
        to = next((v for p, v in out if p == "--tw-to"), "transparent")
        out = [(p, "linear-gradient(90deg, %s, %s)" % (frm, to) if p == "background-image" else v) for p, v in out]
    return out


def is_gray(value: str) -> Optional[bool]:
    """Для меток tw(): серый ли это текст средней светлоты (не почти белый и не почти чёрный)."""
    m = re.fullmatch(r"tw\((\w+)-(\d+)\)", value.strip())
    if not m:
        return None
    return m.group(1) in GRAYS and 300 <= int(m.group(2)) <= 600


def is_colored(value: str) -> Optional[bool]:
    """Для меток tw(): цветная ли заливка (не серое семейство, не бледный оттенок 50–100)."""
    m = re.fullmatch(r"tw\((\w+)-(\d+)\)", value.strip())
    if not m:
        return None
    return m.group(1) not in GRAYS and 200 <= int(m.group(2)) <= 900
