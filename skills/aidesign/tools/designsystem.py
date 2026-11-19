#!/usr/bin/env python3
"""Дизайн-система проекта для AI Design: токены, проверка «мимо токенов», архив.

    python3 designsystem.py export --root .
    python3 designsystem.py check <пути сайта…> --ds design-system [--json]
    python3 designsystem.py pack --root . --slug S

`design-system/tokens.css` — источник: `:root { --… }`, тёмная тема —
`[data-theme=dark]` или `@media (prefers-color-scheme: dark)`. export выводит из него
`tokens.json` по префиксам --color-, --font-, --space-, --radius-, --shadow-, --motion-
(остальное — other), темы — в "$themes". check ищет: переменная не объявлена
(ds-undefined-var), цвет или шрифт мимо токенов (ds-hardcoded-color, ds-hardcoded-font),
токен нигде не используется (ds-unused-token); вывод и `aidesign-ignore` — как у check.py.
pack кладёт `design-system-<slug>-<дата>.zip` (design-system/ и DESIGN.md) рядом с проектом —
в его родительскую папку; есть такое имя — добавляет -2, -3, ничего не перезаписывает.
Коды выхода: 0 — хорошо, 1 — есть находки / нечего упаковать, 2 — ошибка ввода.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check as checkpy  # noqa: E402  — формат находок и разбор CSS общие с check.py (лежит рядом)

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

GROUPS = ("color", "font", "space", "radius", "shadow", "motion")
VAR_DECL = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+)")
VAR_USE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|(?<![\w-])(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(([^()]*)\)", re.I)
WORD = re.compile(r"(?<![\w-])([a-zA-Z]+)(?![\w(-])")      # отдельное слово: не часть --имени и не функция
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'|url\([^)]*\)")
# Названия цветов CSS Color 4 (transparent, currentColor, inherit — не цвета мимо токенов).
NAMED = set((
    "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown "
    "burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan "
    "darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred "
    "darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink "
    "deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold "
    "goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush "
    "lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey "
    "lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow "
    "lime limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen "
    "mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin "
    "navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise "
    "palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue "
    "saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow "
    "springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen").split())
# Свойства, где слово — это цвет; в остальных (animation, grid-area, font) имя цвета — просто имя.
COLOR_PROPS = re.compile(r"^(?:--.*|color|background(?:-color)?|border(?:-(?:top|right|bottom|left|block|inline)"
                         r"(?:-(?:start|end))?)?(?:-color)?|outline(?:-color)?|fill|stroke|caret-color|accent-color|"
                         r"column-rule(?:-color)?|text-decoration(?:-color)?|text-emphasis(?:-color)?|"
                         r"(?:box|text)-shadow|flood-color|lighting-color|stop-color|scrollbar-color)$", re.I)
FONT_KEYWORDS = {"inherit", "initial", "unset", "revert", "revert-layer"}
REF = "design-system/README.md"
RULES = {
    "ds-undefined-var": ("переменная %s не объявлена ни в tokens.css, ни на сайте", "объявить токен в design-system/tokens.css или взять существующий"),
    "ds-hardcoded-color": ("цвет %s задан мимо токенов", "взять var(--color-…) из design-system/tokens.css или завести новый токен"),
    "ds-hardcoded-font": ("шрифт %s задан мимо токенов", "font-family: var(--font-…) из design-system/tokens.css"),
    "ds-unused-token": ("токен %s нигде на сайте не используется", "использовать его или убрать из tokens.css (с записью в CHANGELOG.md)"),
}


class InputError(Exception):
    pass


# ── токены ──────────────────────────────────────────────────────────────────

def _blocks(css: str):
    """(селектор с охватом @media, тело) для каждого блока объявлений."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    stack, start, out = [], 0, []
    for i, ch in enumerate(css):
        if ch == "{":
            stack.append(" ".join(css[start:i].split()))
            start = i + 1
        elif ch == "}":
            if stack:
                out.append((" ".join(stack), css[start:i]))
                stack.pop()
            start = i + 1
    return out


def parse_tokens(css_text: str) -> Dict[str, Dict[str, str]]:
    """{"base": {--имя: значение}, "dark": {...}}."""
    out = {"base": {}, "dark": {}}
    for sel, body in _blocks(css_text):
        low = sel.lower().replace(" ", "")
        dark = "prefers-color-scheme:dark" in low or re.search(r"data-theme=[\"']?dark", low)
        if not dark and ":root" not in low and not low.startswith("html"):
            continue
        for name, value in VAR_DECL.findall(body):
            out["dark" if dark else "base"][name] = " ".join(value.split())
    return out


def group(tokens: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    out = {g: {} for g in GROUPS + ("other",)}
    for name, value in tokens.items():
        g = next((g for g in GROUPS if name.startswith("--%s-" % g)), "other")
        out[g][name[len("--%s-" % g):] if g != "other" else name[2:]] = value
    return out


def tokens_path(root: str) -> str:
    p = os.path.join(root, "design-system", "tokens.css")
    if not os.path.isfile(p):
        raise InputError("нет %s — дизайн-система начинается с tokens.css" % p)
    return p


def export(root: str) -> str:
    with open(tokens_path(root), encoding="utf-8") as f:
        t = parse_tokens(f.read())
    data = group(t["base"])
    if t["dark"]:
        data["$themes"] = {"dark": {g: v for g, v in group(t["dark"]).items() if v}}
    out = os.path.join(root, "design-system", "tokens.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out


# ── проверка «мимо токенов» ─────────────────────────────────────────────────

def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def _hit(doc, rule: str, line: int, what: str) -> List[checkpy.Finding]:
    ignored = doc.ignores.get(line, set())
    if rule in ignored or "all" in ignored:
        return []
    msg, fix = RULES[rule]
    return [checkpy.Finding(str(doc.path), line, rule, msg % what, fix, REF)]


def _hardcoded_color(prop: str, value: str):
    """Первый цвет, заданный мимо токенов: hex, функция цвета без var() или название цвета."""
    plain = QUOTED.sub("", value)
    for m in COLOR.finditer(plain):
        if m.group(1) is None or "var(" not in m.group(1):
            return m.group(0)
    if COLOR_PROPS.match(prop):
        bare = re.sub(r"--[\w-]+", "", plain)                 # имена переменных — не цвета
        for m in WORD.finditer(bare):
            if m.group(1).lower() in NAMED:
                return m.group(1)
    return None


def _site_findings(doc, declared) -> List[checkpy.Finding]:
    out = []
    for d in doc.decls:
        for name in VAR_USE.findall(d.value):
            if name not in declared:
                out += _hit(doc, "ds-undefined-var", d.line, name)
        color = _hardcoded_color(d.prop, d.value)
        if color:
            out += _hit(doc, "ds-hardcoded-color", d.line, color)
        if d.prop in ("font-family", "font") and "var(" not in d.value and d.value.lower() not in FONT_KEYWORDS:
            out += _hit(doc, "ds-hardcoded-font", d.line, d.value)
    return out


def check(site_paths, ds_root) -> List[checkpy.Finding]:
    ds = Path(ds_root)
    tfile = ds / "tokens.css"
    if not tfile.is_file():
        raise InputError("нет %s" % tfile)
    tdoc = checkpy.Doc(tfile, tfile.read_text(encoding="utf-8"))
    tokens = parse_tokens(tdoc.text)
    docs = [checkpy.Doc(f, f.read_text(encoding="utf-8", errors="replace"))
            for f in checkpy.collect_files(site_paths) if not _inside(f, ds)]
    declared = set(tokens["base"]) | set(tokens["dark"])
    used = set(VAR_USE.findall(tdoc.text))                # токен из токена — тоже использование
    for doc in docs:
        declared |= {d.prop for d in doc.decls if d.prop.startswith("--")}
        used |= {n for d in doc.decls for n in VAR_USE.findall(d.value)}
    findings = []
    for doc in docs:
        findings += _site_findings(doc, declared)
    for d in tdoc.decls:
        if d.prop in tokens["base"] and d.prop not in used and not any(
                f.rule == "ds-unused-token" and d.prop in f.message for f in findings):
            findings += _hit(tdoc, "ds-unused-token", d.line, d.prop)
    findings.sort(key=lambda x: (x.path, x.line, x.rule))
    return findings


# ── архив ───────────────────────────────────────────────────────────────────

def pack(root: str, slug: str) -> str:
    ds, design = os.path.join(root, "design-system"), os.path.join(root, "DESIGN.md")
    if not os.path.isdir(ds) or not os.path.isfile(design):
        raise FileNotFoundError("для архива нужны design-system/ и DESIGN.md в %s" % root)
    if os.path.isfile(os.path.join(ds, "tokens.css")):
        export(root)                                       # tokens.json — свежий, из того же источника
    stem = "design-system-%s-%s" % (re.sub(r"[^\w.-]+", "-", slug, flags=re.U), dt.date.today().isoformat())
    parent = os.path.dirname(os.path.abspath(root).rstrip(os.sep)) or os.path.abspath(root)
    out, n = os.path.join(parent, stem + ".zip"), 2
    while os.path.lexists(out):                            # чужой или прошлый архив не перезаписываем
        out, n = os.path.join(parent, "%s-%d.zip" % (stem, n)), n + 1
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as z:
        z.write(design, "DESIGN.md")
        for base, dirs, names in os.walk(ds):
            dirs.sort()
            for n in sorted(names):
                if n != ".DS_Store":
                    p = os.path.join(base, n)
                    z.write(p, os.path.relpath(p, root).replace(os.sep, "/"))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Дизайн-система проекта (AI Design)")
    sub = p.add_subparsers(dest="cmd")
    e = sub.add_parser("export")
    e.add_argument("--root", default=".")
    c = sub.add_parser("check")
    c.add_argument("paths", nargs="+")
    c.add_argument("--ds", default="design-system")
    c.add_argument("--json", action="store_true")
    k = sub.add_parser("pack")
    k.add_argument("--root", default=".")
    k.add_argument("--slug", required=True)
    try:
        a = p.parse_args(argv)
    except SystemExit as err:
        return 2 if err.code else 0
    try:
        if a.cmd == "export":
            print("tokens.json обновлён: %s" % export(os.path.abspath(a.root)))
            return 0
        if a.cmd == "pack":
            print("Архив: %s" % pack(os.path.abspath(a.root), a.slug))
            return 0
        if a.cmd != "check":
            p.print_help()
            return 2
        findings = check(a.paths, a.ds)
    except InputError as err:
        print("Ошибка: %s" % err, file=sys.stderr)
        return 2
    except FileNotFoundError as err:
        print("Ошибка: %s" % err, file=sys.stderr)
        return 1 if a.cmd == "pack" else 2
    if a.json:
        print(json.dumps({"count": len(findings), "findings": [asdict(f) for f in findings]}, ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print("%s:%d — [%s] %s — %s" % (f.path, f.line, f.rule, f.message, f.fix))
        print("Находок: %d" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
