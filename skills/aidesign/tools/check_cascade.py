# По мотивам: pbakaus/impeccable (Apache-2.0) — crates/core/src/checks/{rules,measures}.rs, crates/html/src/*;
# код написан заново, пороги (WCAG, 1.25×, 72px/40 знаков, 11px) — из источника.
"""Правила check.py, которым нужен каскад: дерево разметки и итоговые значения элементов.

Контраст по WCAG, серый на цветном, вложенные карточки, плоская иерархия кеглей, огромный h1,
курсив-засечки в заголовке, мелкий интерфейсный текст, тесные поля, повтор текста в одной
карточке, позиционированный слой под overflow: hidden. Дерево строит check_dom.py.
"""

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import check_dom as cd
import check_tailwind as tw

Hit = Tuple[int, str]
SKIP_TAGS = {"script", "style", "head", "title", "template", "noscript", "option", "svg", "math", "code", "pre"}
SR_ONLY = re.compile(r"\b(sr-only|visually-hidden|screen-reader|a11y-hidden)\b")
SERIFS = {"fraunces", "recoleta", "newsreader", "playfair display", "playfair", "cormorant", "cormorant garamond",
          "garamond", "eb garamond", "tiempos", "tiempos headline", "lora", "vollkorn", "spectral", "source serif 4",
          "source serif pro", "ibm plex serif", "merriweather", "libre caslon", "libre baskerville", "baskerville",
          "georgia", "times new roman", "times", "dm serif display", "instrument serif", "pt serif", "noto serif",
          "literata", "alegreya", "prata", "playfair display sc", "serif", "ui-serif"}


def tree(core, doc) -> Optional[cd.Node]:
    if not hasattr(doc, "_dom"):
        doc._dom = None
        if doc.is_html and doc.markup.strip():
            sheets = []
            for m in re.finditer(r"<link\b[^>]*>", doc.markup, re.I):
                tag = m.group(0)
                href = re.search(r"href\s*=\s*[\"']([^\"'#?]+)", tag)
                if re.search(r"stylesheet", tag, re.I) and href and not re.match(r"[a-z]+:|//", href.group(1)):
                    p = Path(doc.path).parent / href.group(1)
                    if p.is_file():
                        sheets.append(core.Doc(p, p.read_text(encoding="utf-8", errors="replace")).decls)
            doc._dom = cd.build(doc, sheets)
    return doc._dom


def hidden(node: cd.Node) -> bool:
    for n in [node] + list(node.ancestors()):
        st = n.style
        if n.tag in SKIP_TAGS or "hidden" in n.attrs or n.attrs.get("aria-hidden") == "true" \
                or st.get("display") == "none" or st.get("visibility") == "hidden" \
                or SR_ONLY.search(" ".join(n.classes)) or re.fullmatch(r"0(\.0+)?", st.get("opacity", "1").strip()) \
                or "disabled" in n.attrs or n.attrs.get("aria-disabled") == "true":
            return True
    return False


def text_nodes(root: cd.Node):
    for n in root.walk():
        if n.tag != "#root" and re.search(r"[^\W\d_]", n.text) and not hidden(n):
            yield n


def spread(c) -> float:
    return max(c[:3]) - min(c[:3])


def light(c) -> float:
    return (max(c[:3]) + min(c[:3])) / 510


def lum(c) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def blend(top, under):
    a = top[3]
    return tuple(top[i] * a + under[i] * (1 - a) for i in range(3)) + (1.0,)


def background(node: cd.Node):
    """('rgb', (r,g,b,1)) | ('tw', 'tw(blue-600)') | ('complex', None) — что под текстом в покое."""
    layers = []
    for n in [node] + list(node.ancestors()):
        img = n.style.get("background-image", "none")
        raw = cd.resolve(n, n.style.get("background-color", "")).strip()
        if raw.startswith("tw("):
            return ("tw", raw) if not layers else ("complex", None)
        if img not in {"none", ""} and ("gradient(" in img or "url(" in img):
            return ("complex", None)
        c = cd.rgba(raw) if raw else None
        if raw and c is None and raw not in {"inherit", "initial", "unset"}:
            return ("complex", None)
        if c and c[3] > 0:
            layers.append(c)
            if c[3] >= 0.999:
                break
    base = (255, 255, 255, 1.0)
    for c in reversed(layers):
        base = blend(c, base)
    return ("rgb", base)


def foreground(node: cd.Node):
    raw, origin = cd.inherited(node, "color")
    raw = raw.strip()
    if raw.startswith("tw("):
        return ("tw", raw)
    fill, _ = cd.inherited(node, "-webkit-text-fill-color")
    if fill.strip() == "transparent":
        return ("complex", None)
    c = cd.rgba(raw) if raw else (0, 0, 0, 1.0)
    if c is None:
        return ("complex", None)
    alpha = c[3]
    for n in [node] + list(node.ancestors()):
        op = re.fullmatch(r"\s*(0?\.\d+|1(\.0+)?)\s*", n.style.get("opacity", "1"))
        if op:
            alpha *= float(op.group(1))
        if "text" in n.style.get("background-clip", "") or "text" in n.style.get("-webkit-background-clip", ""):
            return ("complex", None)
    return ("rgb", c[:3] + (alpha,))


def _desc(n: cd.Node) -> str:
    cls = sorted(n.classes)
    return "<%s%s>" % (n.tag, ("." + cls[0]) if cls else "")


def c_low_contrast(core, doc) -> List[Hit]:
    root = tree(core, doc)
    if root is None:
        return []
    seen: Dict[tuple, list] = {}
    for n in text_nodes(root):
        kind_f, fg = foreground(n)
        kind_b, bg = background(n)
        if kind_f != "rgb" or kind_b != "rgb" or fg[3] <= 0.02:
            continue
        ink = blend(fg, bg)
        hi, lo = sorted((lum(ink), lum(bg)), reverse=True)
        ratio = (hi + 0.05) / (lo + 0.05)
        size = cd.font_px(n, "min")
        weight = cd.inherited(n, "font-weight")[0] or ("700" if n.tag in cd.UA_BOLD else "400")
        bold = weight in {"bold", "bolder"} or (weight.isdigit() and int(weight) >= 700)
        need = 3.0 if size >= 24 or (bold and size >= 18.66) else 4.5
        if ratio < need:
            key = (tuple(round(x) for x in ink[:3]), tuple(round(x) for x in bg[:3]), need)
            seen.setdefault(key, []).append((n.line, "%.2f:1 при норме %g:1, %s" % (ratio, need, _desc(n))))
    return [(v[0][0], v[0][1] + (" и ещё %d" % (len(v) - 1) if len(v) > 1 else "")) for v in seen.values()]


def c_gray_on_color(core, doc) -> List[Hit]:
    root = tree(core, doc)
    if root is None:
        return []
    seen: Dict[tuple, list] = {}
    for n in text_nodes(root):
        kind_f, fg = foreground(n)
        kind_b, bg = background(n)
        gray = tw.is_gray(fg) if kind_f == "tw" else (kind_f == "rgb" and fg[3] >= 0.5 and spread(fg) <= 30
                                                       and 0.3 < light(fg) < 0.9)
        color = tw.is_colored(bg) if kind_b == "tw" else (kind_b == "rgb" and spread(bg) >= 60)
        if gray and color:
            key = (str(fg), str(bg))
            seen.setdefault(key, []).append((n.line, "%s" % _desc(n)))
    return [(v[0][0], v[0][1] + (" и ещё %d" % (len(v) - 1) if len(v) > 1 else "")) for v in seen.values()]


def thin_border_row(core, doc) -> List[Hit]:
    import check_boxes as cb
    return cb.c_thin_border_row(core, doc)


def build(core) -> list:
    import check_boxes as cb                    # здесь, а не сверху: check_boxes сам импортирует этот модуль
    R = core.R

    def bind(fn):
        return lambda doc: fn(core, doc)

    return [
        R("low-contrast", "low-contrast", "контраст текста ниже WCAG AA (4.5:1, крупный — 3:1)",
          "темнее текст или светлее фон; проверить пары цветов в tokens.css", bind(c_low_contrast), True),
        R("gray-on-color", "gray-on-color", "серый текст на цветном фоне",
          "оттенок цвета фона или почти белый", bind(c_gray_on_color), True),
        R("nested-cards", "nested-cards", "карточка в карточке",
          "внутри карточки — интервалы, типографика, разделители", bind(cb.c_nested_cards), True),
        R("cramped-padding", "cramped-padding", "текст прижат к краю своей плашки или рамки",
          "поле не меньше четверти кегля, у кнопок — от 0.75em по бокам", bind(cb.c_cramped), True),
        R("clipped-overflow-container", "clipped-overflow", "выпадающий слой обрезан overflow: hidden",
          "overflow: visible у контейнера или слой вынести из обрезки", bind(cb.c_clipped), True),
        R("repeated-container-text", "repeated-container-text", "одна и та же надпись трижды в одной карточке",
          "сказать один раз, там, где она нужна", bind(cb.c_repeated_text), True),
        R("flat-type-hierarchy", "flat-hierarchy", "кегли заголовков и текста различаются меньше чем в 1.25 раза",
          "модульная шкала, хотя бы один сильный шаг (типографика.md)", bind(cb.c_flat_hierarchy), True),
        R("oversized-h1", "oversized-h1", "длинный заголовок огромным кеглем занимает экран",
          "короткий заголовок крупно или длинный — умеренно (до ~6rem)", bind(cb.c_oversized_h1), True),
        R("italic-serif-display", "italic-serif", "огромный курсивный заголовок с засечками",
          "прямое начертание или другой класс гарнитуры", bind(cb.c_italic_serif), True),
        R("undersized-ui-text", "undersized-ui-text", "текст ссылки, кнопки или подписи мельче 11px",
          "интерфейсный текст от 12–13px", bind(cb.c_undersized_ui), True),
    ]
