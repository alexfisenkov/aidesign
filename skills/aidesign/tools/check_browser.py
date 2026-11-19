# По мотивам: pbakaus/impeccable (Apache-2.0) — браузерные правила crates/core/src/browser/*; код написан заново.
"""check.py --browser: правила раскладки по отрисовке через общий браузерный модуль (browser.py).

Страница открывается на 1280×800 и 390×844 (browser/layout.mjs). Чужой сайт — только если
robots.txt разрешает (агент AIDesign); `--own-site` — сайт человека, по его слову. Нет Node,
пакета или браузера — понятный отказ и код 2 (поставить: python3 browser.py ensure).
"""

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import List, Optional, Tuple

LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
SPECS = [
    ("script-error", "script-error", "скрипт упал при загрузке страницы", "починить ошибку до оценки остального"),
    ("text-overflow", "text-overflow", "текст вылезает за край или обрезан", "перенос строк, ограничить ширину или осознанная прокрутка"),
    ("body-text-viewport-edge", "viewport-edge", "абзац прижат к краю экрана", "поля контейнера от 16px (на телефоне от 12px)"),
    ("text-occlusion", "text-occlusion", "текст закрыт другим элементом", "развести слои или убрать текст из-под слоя"),
    ("line-length", "long-measure", "строки длиннее 80 знаков по отрисовке", "max-width 65–75ch у текста"),
    ("straggler", "straggler", "в последней строке абзаца одно слово", "text-wrap: pretty у абзацев или правка фразы"),
    ("unbalanced-heading", "unbalanced-heading", "заголовок переносится с огрызком в последней строке", "text-wrap: balance у заголовков"),
    ("heading-rhythm", "monotonous-spacing", "заголовки прижаты к блоку выше", "над заголовком места больше, чем под ним"),
    ("content-hidden-at-rest", "section-fade", "текст остаётся невидимым после прокрутки", "видим по умолчанию, анимация только добавляет"),
    ("edge-flush-cards", "edge-flush-cards", "карточки ленты срезаны краем", "отступ у ленты или ширина по видимой области"),
    ("first-viewport-column-overflow", "column-overflow", "на первом экране одна колонка уходит далеко вниз", "уравнять колонки или ограничить высоту"),
]


def rules(core) -> list:
    return [core.R(rid, anchor, desc, advice, lambda doc: []) for rid, anchor, desc, advice in SPECS]


def robots_allows(url: str) -> Tuple[Optional[bool], str]:
    """RFC 9309: нет файла (4xx) — можно; 401/403 и 5xx — нельзя; не достучались — None."""
    parts = urllib.parse.urlsplit(url)
    robots = "%s://%s/robots.txt" % (parts.scheme, parts.netloc)
    req = urllib.request.Request(robots, headers={"User-Agent": "AIDesign (+check; respects robots.txt)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            lines = r.read(512 * 1024).decode("utf-8", "replace").splitlines()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) or e.code >= 500:
            return False, "robots.txt отвечает %d" % e.code
        return True, "robots.txt нет"
    except (urllib.error.URLError, OSError) as e:
        return None, "robots.txt не проверить: %s" % getattr(e, "reason", e)
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(lines)
    return rp.can_fetch("AIDesign", url), "robots.txt"


def targets(paths: List[str], own_site: bool) -> Tuple[List[Tuple[str, str, Optional[str]]], Optional[str]]:
    """(показ, адрес, исходник) по каждой цели; вторым — текст ошибки ввода."""
    out = []
    for raw in paths:
        if re.match(r"https?://", raw, re.I):
            host = urllib.parse.urlsplit(raw).hostname or ""
            if not own_site and host not in LOCAL:
                ok, why = robots_allows(raw)
                if ok is None:
                    return [], "%s — %s; свой сайт — флаг --own-site" % (raw, why)
                if not ok:
                    return [], "%s — %s запрещает; свой сайт — флаг --own-site" % (raw, why)
            out.append((raw, raw, None))
            continue
        p = Path(raw)
        if not p.exists():
            return [], "нет такого пути: %s" % raw
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*.htm*") if "node_modules" not in f.parts
                                                 and not any(x.startswith(".") for x in f.relative_to(p).parts))
        for f in files:
            if f.suffix.lower() not in {".html", ".htm"}:
                return [], "%s: браузером проверяются страницы .html или адреса http(s)" % f
            out.append((str(f), f.resolve().as_uri(), f.read_text(encoding="utf-8", errors="replace")))
    if not out:
        return [], "нет страниц .html для проверки"
    return out, None


def locate(source: Optional[str], f: dict) -> int:
    if not source:
        return 0
    lines = source.split("\n")
    pats = []
    if f.get("id"):
        pats.append(r"\sid\s*=\s*[\"']%s[\"']" % re.escape(f["id"]))
    if f.get("cls"):
        pats.append(r"<%s\b[^>]*class\s*=\s*[\"'][^\"']*\b%s\b" % (re.escape(f.get("tag") or "\\w+"), re.escape(f["cls"])))
    words = " ".join((f.get("text") or "").split()[:4])
    if len(words) >= 6:
        pats.append(re.escape(words))
    if f.get("tag"):
        pats.append(r"<%s\b" % re.escape(f["tag"]))
    for pat in pats:
        for i, line in enumerate(lines, 1):
            if re.search(pat, line):
                return i
    return 1


def run_cli(core, paths: List[str], own_site: bool = False):
    """(код, находки): код 2 — ошибка ввода или нет браузера; находки — в формате check.Finding."""
    found, err = targets(paths, own_site)
    if err:
        print("Ошибка: %s" % err, file=sys.stderr)
        return 2, []
    try:
        import browser
    except ImportError:
        print("Ошибка: рядом с check.py нет browser.py и папки browser/.", file=sys.stderr)
        return 2, []
    if not browser.ready():
        print("Нет браузерного модуля: проверка раскладки невозможна. Что есть и чего нет: "
              "python3 browser.py doctor; поставить (после «да» человека): python3 browser.py ensure --yes. "
              "Статическая проверка работает и без него: python3 check.py <папка>.", file=sys.stderr)
        return 2, []
    try:
        data = browser.run("layout.mjs", {"targets": [u for _, u, _ in found]}, timeout=90 + 45 * len(found))
    except browser.BrowserError as e:
        print("Ошибка браузера: %s" % e, file=sys.stderr)
        return 2, []
    spec = {s[0]: s for s in SPECS}
    by_url = {u: (shown, src) for shown, u, src in found}
    out, seen = [], set()
    for res in data.get("results", []):
        shown, src = by_url.get(res.get("target"), (res.get("target"), None))
        vp = "×".join(str(x) for x in res.get("viewport", []))
        if res.get("error"):
            print("Не открылась %s (%s): %s" % (shown, vp, res["error"]), file=sys.stderr)
            return 2, []
        for f in res.get("findings", []):
            rid = f.get("rule")
            if rid not in spec:
                continue
            line = locate(src, f)
            key = (shown, line, rid, f.get("tag"), f.get("cls"))
            if key in seen:
                continue
            seen.add(key)
            what = "<%s%s>" % (f.get("tag") or "", "." + f["cls"] if f.get("cls") else "") if f.get("tag") else ""
            msg = "%s (%s)" % (spec[rid][2], ", ".join(x for x in (what, f.get("detail", ""), vp) if x))
            out.append(core.Finding(shown, line, rid, msg, spec[rid][3], "антипаттерны.md#" + spec[rid][1]))
    out.sort(key=lambda x: (x.path, x.line, x.rule))
    return 0, out
