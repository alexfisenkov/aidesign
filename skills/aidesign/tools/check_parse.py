"""Разбор компонентов для check.py: JSX/TSX, Vue, Svelte, Astro, CSS-in-JS, классы Tailwind.

Всё сохраняет смещения исходника (вырезанное заменяется пробелами), поэтому номера строк
находок указывают в настоящий файл. Заполняет у Doc: markup (разметка без кода), visible
(видимый текст без выражений {…}), scripts, decls (из <style>, styled`…`, css`…`,
style={{…}} и классов Tailwind). Только стандартная библиотека.
"""

import re
from typing import List, Tuple

import check_tailwind as tw

STYLED = re.compile(
    r"\b(?:styled(?:\.[A-Za-z]\w*|\([^()]*\))(?:\.attrs\((?:[^()]|\([^()]*\))*\))?|css|createGlobalStyle|"
    r"injectGlobal|keyframes)\s*`([^`]*)`")
JSX_TAG = re.compile(
    r"<(/?)([A-Za-z][\w.:-]*)?((?:\s+(?:\{\.\.\.[^{}]*\}|[\w:@.-]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|"
    r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}))?))*)\s*(/?)>")
CLASS_ATTR = re.compile(
    r"(?<![\w:-])(?:class|className)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|\{\s*[\"'`]([^\"'`]*)[\"'`]\s*\})")
CLASS_CALL = re.compile(r"\b(?:cn|clsx|classnames|classNames|twMerge|twJoin|cx|cva)\s*\(")
BIND_CLASS = re.compile(r"(?:\s:class|\sv-bind:class)\s*=\s*\"([^\"]*)\"")
SVELTE_CLASS = re.compile(r"\sclass:([\w-]+)")
STRING = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'|`([^`]*)`")
STYLE_KEY = re.compile(r"([A-Za-z][A-Za-z0-9]*|'[a-z-]+'|\"[a-z-]+\")\s*:\s*(\"[^\"\n]*\"|'[^'\n]*'|`[^`\n]*`|-?\d+(?:\.\d+)?)")
CSS_PROPS = {
    "color", "background", "background-color", "background-image", "background-clip", "border", "border-left",
    "border-right", "border-top", "border-bottom", "border-width", "border-color", "border-radius",
    "border-inline-start", "border-inline-end", "box-shadow", "text-shadow", "font-family", "font-size",
    "font-weight", "font-style", "line-height", "letter-spacing", "text-transform", "text-align",
    "transition", "transition-property", "animation", "animation-name", "opacity", "filter",
    "backdrop-filter", "z-index", "height", "min-height", "max-width", "padding", "padding-left",
    "padding-right", "padding-top", "padding-bottom", "margin", "margin-top", "margin-bottom", "gap",
    "overflow", "position", "top", "left", "right", "bottom", "clip-path", "outline", "display",
}
UNITLESS = {"opacity", "z-index", "font-weight", "line-height"}


def blank(s: str) -> str:
    return re.sub(r"[^\n]", " ", s)


def blank_span(text: str, a: int, b: int) -> str:
    return text[:a] + blank(text[a:b]) + text[b:]


def strip_js_comments(text: str) -> str:
    """Комментарии JS вне строк → пробелы."""
    out, i, n = list(text), 0, len(text)
    quote = ""
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif text.startswith("//", i) and (i == 0 or text[i - 1] != ":"):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = [" "] * (j - i)
            i = j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out[i:j] = [c if c == "\n" else " " for c in text[i:j]]
            i = j
            continue
        i += 1
    return "".join(out)


def mask_expressions(text: str) -> str:
    """Выражения {…} (и {{…}}) → пробелы; незакрытые края куска — тоже."""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\{[^{}]*\}", lambda m: blank(m.group(0)), text)
    text = re.sub(r"\{[^}]*$", lambda m: blank(m.group(0)), text)
    return re.sub(r"^[^{]*\}", lambda m: blank(m.group(0)), text)


def tag_attrs_blanked(tag: str) -> str:
    """Внутри тега значения-выражения {…} — пробелы: в них бывают `>` и код."""
    return re.sub(r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}", lambda m: blank(m.group(0)), tag)


def jsx_markup(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """Разметка JSX: теги и текст между ними, остальное (код) — пробелы. Отдаёт и места тегов."""
    code = strip_js_comments(text)
    out = list(blank(code))
    spans, depth, last = [], 0, None
    for m in JSX_TAG.finditer(code):
        before = code[max(0, m.start() - 40):m.start()].rstrip()
        if depth == 0 and before and (before[-1].isalnum() or before[-1] in "_)]$.") \
                and not re.search(r"\breturn$", before):
            continue                                   # useState<string>(…), a < b — не тег
        closing, name, selfclose = m.group(1), m.group(2), m.group(4)
        if last is not None and depth > 0:
            seg = mask_expressions(code[last:m.start()])
            out[last:m.start()] = list(seg)
        tag = tag_attrs_blanked(m.group(0))
        out[m.start():m.end()] = list(tag)
        spans.append((m.start(), m.end()))
        if closing:
            depth = max(0, depth - 1)
        elif not selfclose and (name or "").lower() not in {"br", "img", "input", "hr", "meta", "link"}:
            depth += 1
        last = m.end()
    return "".join(out), spans


def owner_of(spans: List[Tuple[int, int]], pos: int) -> int:
    for a, b in spans:
        if a <= pos < b:
            return a
    return -1


def class_strings(text: str) -> List[Tuple[int, str]]:
    """(смещение, строка классов) из class/className, :class, class:x, cn()/clsx()."""
    out = []
    for m in CLASS_ATTR.finditer(text):
        val = next(g for g in m.groups() if g is not None)
        out.append((m.start(), re.sub(r"\$\{[^}]*\}", " ", val)))
    for m in BIND_CLASS.finditer(text):
        out.append((m.start(), " ".join(a or b or "" for a, b, _ in STRING.findall(m.group(1)))))
    for m in SVELTE_CLASS.finditer(text):
        out.append((m.start(), m.group(1)))
    for m in CLASS_CALL.finditer(text):
        depth, j = 1, m.end()
        while j < len(text) and depth and j - m.end() < 2000:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        lits = [re.sub(r"\$\{[^}]*\}", " ", next(g for g in s.groups() if g is not None))
                for s in STRING.finditer(text, m.end(), j)]
        out.append((m.start(), " ".join(lits)))
    return out


def load_classes(doc, spans=None) -> None:
    """Классы Tailwind → объявления с хозяином-тегом (owner) и пометкой origin="tw"."""
    for pos, value in class_strings(doc.text):
        decls = tw.decls_for(value.split())
        if not decls:
            continue
        owner = owner_of(spans, pos) if spans is not None else doc.text.rfind("<", 0, pos)
        name = re.match(r"<\s*([A-Za-z][\w.-]*)", doc.text[owner:owner + 60]) if owner >= 0 else None
        selector = (name.group(1).lower() if name else "") + "[class]"
        block = doc.new_block()
        for prop, val in decls:
            doc.add_decl(selector, prop, val, pos, block, owner, "tw")


def kebab(key: str) -> str:
    key = key.strip("'\"")
    return re.sub(r"[A-Z]", lambda m: "-" + m.group(0).lower(), key)


def load_style_objects(doc, code: str, spans) -> None:
    """Объекты стилей: style={{ borderLeft: '4px solid …' }} и const s = { … }."""
    for m in re.finditer(r"\{([^{}]*)\}", code):
        body = m.group(1)
        hits = [(k, v, k_m.start()) for k_m in STYLE_KEY.finditer(body)
                for k, v in [(kebab(k_m.group(1)), k_m.group(2))] if k in CSS_PROPS]
        if not hits:
            continue
        owner = owner_of(spans, m.start())
        block = doc.new_block()
        for prop, raw, at in hits:
            val = raw.strip("'\"`")
            if re.fullmatch(r"-?\d+(?:\.\d+)?", raw) and prop not in UNITLESS:
                val = raw + "px"
            doc.add_decl("[style]", prop, val, m.start(1) + at, block, owner)


def load_component(doc) -> None:
    text, kind = doc.text, doc.kind
    if kind in {".jsx", ".tsx"}:
        markup, spans = jsx_markup(text)
        for m in STYLED.finditer(text):
            doc.parse_css(re.sub(r"\$\{[^}]*\}", lambda x: blank(x.group(0)), m.group(1)), m.start(1), root="&")
        load_style_objects(doc, strip_js_comments(text), spans)
        load_classes(doc, spans)
        doc.scripts = text
        doc.markup = markup
        doc.visible = re.sub(r"<[^>]*>", lambda x: blank(x.group(0)), markup)
        return
    masked = text
    if kind == ".astro":
        masked = re.sub(r"\A\s*---.*?\n---", lambda x: blank(x.group(0)), masked, flags=re.S)
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", masked, re.S | re.I):
        doc.parse_css(m.group(1), m.start(1))
    for m in re.finditer(r"\sstyle\s*=\s*\"([^\"]*)\"", masked, re.I):
        doc.parse_decls("[style]", m.group(1), m.start(1), owner=text.rfind("<", 0, m.start()))
    doc.scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", masked, re.S | re.I))
    masked = re.sub(r"<!--.*?-->", lambda x: blank(x.group(0)), masked, flags=re.S)
    masked = re.sub(r"<(script|style)[^>]*>.*?</\1>", lambda x: blank(x.group(0)), masked, flags=re.S | re.I)
    # Привязки Vue (:x="…", @x="…", v-x="…") и выражения {…} — код, не разметка.
    masked = re.sub(r"(\s(?::|@|v-)[\w:.-]+\s*=\s*)\"[^\"]*\"", lambda x: x.group(1) + blank(x.group(0)[len(x.group(1)):]), masked)
    masked = mask_expressions(masked) if kind != ".vue" else re.sub(r"\{\{.*?\}\}", lambda x: blank(x.group(0)), masked, flags=re.S)
    doc.markup = masked
    doc.visible = re.sub(r"<[^>]*>", lambda x: blank(x.group(0)), masked)
    load_classes(doc)
