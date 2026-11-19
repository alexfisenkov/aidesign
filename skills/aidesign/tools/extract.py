#!/usr/bin/env python3
"""Стиль сайта по ссылке для AI Design: цвета с ролями, шрифты, шкала, отступы, формы, движение.

    python3 extract.py <адрес> [--dark] [--mobile] [--own-site | --allow-local] [--out DIR] [--json]

Открывает страницу в браузере модуля browser.py (Playwright из общего кэша), читает
отрисованные стили и пишет в DIR (по умолчанию .aidesign-work/extract/<домен>-<время>/):
`extract.json` (машине), `report.md` (человеку), `tokens.css` — черновик в формате
design-system/tokens.css (`designsystem.py export` его понимает). Берётся только
наблюдённое; чего на странице не было — названо. Это принципы, не бренд: логотип,
тексты и фирменные шрифты чужого сайта не переносятся; с `--own-site` шапка и отчёт говорят
«снято с вашего сайта» — стиль человека берётся как есть. Чужие файлы с такими именами
в DIR не перезаписываются (код 1).

Честно: без маскировки под человека, User-Agent с пометкой AIDesign. `robots.txt`
уважается — запрет или недоступный robots.txt останавливает (код 1), и так на каждом
переходе страницы, редиректы тоже. Внутренние адреса (этот компьютер, локальная сеть,
служебные адреса облака) не открываются — ни сразу, ни через редирект. Флаги — только по
слову человека: `--own-site` — «сайт мой» (снимает robots.txt и разрешает внутренний адрес,
например localhost), `--allow-local` — только внутренний адрес, robots.txt проверяется.
Окно cookies закрывается кнопкой «принять» и только внутри окна согласия; «отказаться»,
«настроить», кнопки форм не нажимаются. Защиту сайта не обходим.
Коды: 0 — снято, 1 — запрет, браузера нет, страница не открылась, 2 — ошибка ввода.
Эвристика ролей цвета и окна cookies — по мотивам dembrandt (MIT).
"""

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(HERE, "browser"))
import browser  # noqa: E402  — браузерный модуль лежит рядом
import extract_style as style  # noqa: E402  — browser/extract_style.py: разбор снятого, без браузера
import guard  # noqa: E402  — browser/guard.py: внутренние адреса и robots.txt

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

UA = "AIDesign/0.4 (+style reference; respects robots.txt) Python-urllib"
analyze = style.analyze
tokens_css = style.tokens_css
report_md = style.report_md
address_problem = guard.address_problem
robots_allows = guard.robots_allows
# Как узнать свой прошлый результат: по началу файла.
OURS = {"tokens.css": lambda t: "AI Design: снято с" in t[:400],
        "report.md": lambda t: t.startswith("# Стиль с "),
        "extract.json": lambda t: '"source"' in t and '"colors"' in t and '"missing"' in t}


def robots(url: str, allow_local=False) -> str:
    return guard.robots(url, UA, allow_local)


def normalize(url: str):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return guard.canonical_url(url)                       # 0177.0.0.1 → 127.0.0.1, как в браузере


def foreign_files(out: str) -> list:
    found = []
    for name, ours in OURS.items():
        p = os.path.join(out, name)
        if os.path.lexists(p):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                text = ""
            if os.path.islink(p) or not ours(text):
                found.append(name)
    return found


def write_all(out: str, result: dict) -> list:
    os.makedirs(out, exist_ok=True)
    files = []
    for name, text in (("extract.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n"),
                       ("report.md", report_md(result)), ("tokens.css", tokens_css(result))):
        p = os.path.join(out, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(p)
    return files


STOP = {"disallowed": "robots.txt сайта запрещает автоматический просмотр этой страницы",
        "unreachable": "robots.txt сайта не читается (сервер не ответил) — по правилам это запрет"}


def parse(argv):
    ap = argparse.ArgumentParser(description="Стиль сайта по ссылке (AI Design)")
    ap.add_argument("url")
    ap.add_argument("--dark", action="store_true", help="снять и тёмную тему")
    ap.add_argument("--mobile", action="store_true", help="ширина телефона 390")
    ap.add_argument("--own-site", action="store_true",
                    help="сайт человека (по его слову): без robots.txt, внутренний адрес разрешён")
    ap.add_argument("--allow-local", action="store_true",
                    help="внутренний адрес разрешён (по слову человека), robots.txt проверяется")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=int, default=180)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    try:
        a = parse(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    url = normalize(a.url)
    if not url:
        print("Ошибка: нужен адрес сайта http:// или https://", file=sys.stderr)
        return 2
    domain = urllib.parse.urlsplit(url).hostname
    out = a.out or os.path.join(".aidesign-work", "extract",
                                "%s-%s" % (domain, dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    local = a.own_site or a.allow_local

    def fail(msg):
        if a.json:
            print(json.dumps({"ok": False, "error": msg, "out": out}, ensure_ascii=False))
        else:
            print("! " + msg)
        return 1

    foreign = foreign_files(out)
    if foreign:
        return fail("в %s уже есть чужие %s — не перезаписываю; выберите другую папку --out"
                    % (out, ", ".join(foreign)))
    why = None if local else address_problem(url)
    if why:
        return fail("%s. Внутренние адреса не открываем. Если это сайт человека у него на компьютере "
                    "или в его сети и он сам это сказал — повторите с --own-site или --allow-local." % why)
    state = "own-site" if a.own_site else robots(url, local)
    if state in STOP:
        return fail("%s. Стиль не снят. Если это сайт человека — повторите с --own-site; "
                    "иначе попросите скриншоты." % STOP[state])
    try:
        raw = browser.run("extract.mjs", {"url": url, "dark": a.dark, "mobile": a.mobile, "ownSite": a.own_site,
                                          "allowLocal": local, "timeoutMs": max(10, a.timeout - 30) * 1000},
                          timeout=a.timeout)
    except browser.BrowserError as e:
        return fail("страница не прочитана: %s" % e)
    result = analyze(raw, url=url, robots=state, mobile=a.mobile, dark_requested=a.dark)
    files = write_all(out, result)
    prim = next((c for c in result["colors"] if c["role"] == "primary"), None)
    if a.json:
        print(json.dumps({"ok": True, "out": out, "files": files, "robots": state,
                          "primary": prim and prim["hex"], "missing": result["missing"]}, ensure_ascii=False))
        return 0
    print("Снято с %s%s: %s" % ("вашего сайта " if a.own_site else "", domain, out))
    print("  основной цвет: %s" % ("%s (%s)" % (prim["hex"], prim["why"]) if prim else "не найден"))
    print("  не наблюдалось: %s" % (", ".join(result["missing"]) or "—"))
    print("  человеку — report.md; черновик токенов — tokens.css (%s)"
          % ("ваш стиль как есть" if a.own_site else "принципы, не бренд"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
