#!/usr/bin/env python3
"""Снимки превью AI Design: компьютер 1280 и телефон 390 — картинками рядом с файлом.

    python3 .aidesign-work/shots.py .aidesign-work/<dir>/rounds/01/a.html [b.html c.html] [--json]

Кладёт rounds/01/a-1280.png и a-390.png рядом с превью. `ad.py round option` подхватывает
их сам. Снимок нужен, чтобы человек видел варианты в любом браузере: встроенный браузер
приложения может не пускать живое превью в рамку панели.

Снимает Chromium через Playwright (`npx --no-install playwright screenshot`); браузера Playwright
нужной версии нет — пробует Chrome и Edge компьютера (`--channel`). Нет Node.js или браузера —
понятный отказ с кодом 1, прогон идёт дальше: превью смотрят живыми на панели или кнопкой
«Открыть в новой вкладке». Коды: 0 — все снимки сняты, 1 — нет Playwright или снимок не вышел,
2 — ошибка ввода. Только стандартная библиотека Python 3.9+.
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SIZES = (("shot1280", 1280, 800), ("shot390", 390, 844))
WAIT_MS = 800                                             # входная анимация успевает доиграть
TIMEOUT_S = 180
NO_SHOTS = ("снимков не будет — прогон идёт дальше: превью видно живым на панели "
            "и кнопкой «Открыть в новой вкладке»")


def which(name):
    """npx — с PATH; AIDESIGN_SHOTS_PATH подменяет PATH только для тестов."""
    return shutil.which(name, path=os.environ.get("AIDESIGN_SHOTS_PATH") or None)


# Браузер Playwright другой версии, чем пакет, — частый случай: тогда пробуем Chrome и Edge,
# что уже стоят на компьютере (`--channel`). Ничего не скачиваем: `npx --no-install`.
CHANNELS = (None, "chrome", "msedge")


def missing_tool():
    """Чего не хватает для снимков — строкой человеку, или None."""
    if not which("npx"):
        return ("Playwright недоступен: нет Node.js (npx) — %s. "
                "Поставить: python3 .aidesign-work/setup.py plan node playwright" % NO_SHOTS)
    return None


def first_error(text, code):
    """Строка ошибки из вывода Playwright: «Error: …», а не рамка из ═ под ней."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for x in lines:
        if re.match(r"(Error|error)\b", x) or "Executable doesn't exist" in x:
            return x
    words = [x for x in lines if re.search(r"\w", x)]
    return words[-1] if words else "код %d" % code


def shoot_once(npx, page, out, width, height, channel):
    cmd = [npx, "--no-install", "playwright", "screenshot"] + (["--channel", channel] if channel else []) + [
        "--viewport-size", "%d,%d" % (width, height), "--wait-for-timeout", str(WAIT_MS),
        pathlib.Path(page).resolve().as_uri(), out]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    if r.returncode != 0 or not os.path.isfile(out):
        return first_error((r.stderr or "") + "\n" + (r.stdout or ""), r.returncode)
    return None


def shoot(npx, page, out, width, height):
    """Один снимок; None — получилось, иначе текст первой ошибки (браузер Playwright)."""
    first = None
    for channel in CHANNELS:
        err = shoot_once(npx, page, out, width, height, channel)
        if not err:
            return None
        first = first or err
    if "Executable doesn't exist" in first:
        first += " (браузер не скачан под эту версию Playwright: npx playwright install chromium)"
    return first


def take(pages):
    """(снимки, ошибка): по записи {file, shot1280, shot390} на превью; на первой ошибке — стоп."""
    why = missing_tool()
    if why:
        return [], why
    npx, done = which("npx"), []
    for page in pages:
        stem = os.path.splitext(page)[0]
        rec = {"file": page}
        for key, w, h in SIZES:
            out = "%s-%d.png" % (stem, w)
            err = shoot(npx, page, out, w, h)
            if err:
                return done, "снимок %s (%d) не вышел: %s — %s" % (os.path.basename(page), w, err, NO_SHOTS)
            rec[key] = out
        done.append(rec)
    return done, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Снимки превью 1280 и 390 рядом с файлом")
    ap.add_argument("pages", nargs="+", help="HTML-файлы превью")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    lost = [p for p in a.pages if not os.path.isfile(p)]
    if lost:
        print("нет файла: %s" % ", ".join(lost), file=sys.stderr)
        return 2
    done, err = take(a.pages)
    if a.json:
        print(json.dumps({"ok": not err, "shots": done, "error": err}, ensure_ascii=False))
    else:
        for rec in done:
            print("снимки: %s, %s" % (rec["shot1280"], rec["shot390"]))
        if done:
            print("· ad.py round option подхватит их сам: файлы лежат рядом с превью")
        if err:
            print("! " + err)
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
