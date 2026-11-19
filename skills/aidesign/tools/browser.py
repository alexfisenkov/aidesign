#!/usr/bin/env python3
"""Общий браузерный модуль AI Design: Playwright (Node) в общем кэше скилла, один раз на компьютер.

    python3 browser.py doctor [--json]       — что есть, чего нет; ничего не ставит
    python3 browser.py ensure [--yes] [--json] — без --yes только план; с --yes ставит и проверяет

Пакет `playwright` ставится не в проект, а в общий кэш: `~/.cache/aidesign/node`
(Windows — `%LOCALAPPDATA%\\aidesign\\node`). Версия — та же, что у `npx playwright` на
компьютере, чтобы браузер не скачивался второй раз; нет её — последняя. Браузер —
Chromium Playwright, запасной — Chrome или Edge компьютера (`channel`). Скрипты Node лежат
рядом, в папке `browser/`, и находят пакет по переменной AIDESIGN_NODE_HOME.

Без маскировки под человека: User-Agent браузера как есть, с пометкой AIDesign; защиту
сайтов не обходим. Пользуются: extract.py, check.py --browser, film.py seams.
Коды: 0 — готово, 1 — чего-то нет / сбой, 2 — ошибка ввода. Только стандартная библиотека.
Для тестов: AIDESIGN_BROWSER_PATH подменяет PATH, AIDESIGN_BROWSER_HOME — папку кэша.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.environ.get("AIDESIGN_BROWSER_SCRIPTS") or os.path.join(HERE, "browser")
AGENT = "AIDesign"                                         # имя для robots.txt и User-Agent
INSTALL_TIMEOUT = 900
PROBE_TIMEOUT = 90
NODE_MIN = 18                                              # ниже Playwright не работает


class BrowserError(Exception):
    pass


# ── где что ─────────────────────────────────────────────────────────────────

def which(name: str) -> Optional[str]:
    return shutil.which(name, path=os.environ.get("AIDESIGN_BROWSER_PATH") or None)


def cache_dir() -> str:
    if os.environ.get("AIDESIGN_BROWSER_HOME"):
        return os.environ["AIDESIGN_BROWSER_HOME"]
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "aidesign", "node")
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "aidesign", "node")


def _out(cmd: List[str], timeout=30) -> Optional[str]:
    exe = which(cmd[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or "").strip() if r.returncode == 0 else None


def node_version() -> Optional[str]:
    v = _out(["node", "--version"])
    return v.lstrip("v") if v else None


def npx_version() -> Optional[str]:
    """Версия `npx playwright`, если пакет уже есть у человека; ничего не скачивает."""
    if not which("npx"):
        return None
    v = _out(["npx", "--no-install", "playwright", "--version"], timeout=60)
    return v.split()[-1] if v and v.split() else None


def installed_version() -> Optional[str]:
    p = os.path.join(cache_dir(), "node_modules", "playwright", "package.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError):
        return None


def ready() -> bool:
    """Пакет в кэше и Node есть; браузер проверяет doctor."""
    return bool(installed_version() and which("node"))


# ── запуск скрипта ──────────────────────────────────────────────────────────

def _last_json(text: str) -> Optional[dict]:
    for line in reversed([x for x in text.splitlines() if x.strip()]):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def run(script: str, args: Dict, timeout: float = 120) -> dict:
    """Запускает browser/<script> под Node, отдаёт JSON из последней строки вывода."""
    node = which("node")
    if not node:
        raise BrowserError("нет Node.js — поставить: python3 setup.py plan node")
    if not installed_version():
        raise BrowserError("браузерный модуль не поставлен — план: python3 browser.py ensure "
                           "(ставится после «да»: ensure --yes)")
    path = os.path.join(SCRIPTS, script)
    if not os.path.isfile(path):
        raise BrowserError("нет скрипта %s — папка browser/ должна лежать рядом с browser.py" % path)
    env = dict(os.environ, AIDESIGN_NODE_HOME=cache_dir())
    try:
        r = subprocess.run([node, path, json.dumps(args, ensure_ascii=False)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise BrowserError("браузер не уложился в %d с и остановлен" % timeout)
    except OSError as e:
        raise BrowserError("node не запустился: %s" % e)
    data = _last_json(r.stdout or "")
    if data is None:
        tail = [x for x in ((r.stderr or "") + "\n" + (r.stdout or "")).splitlines() if x.strip()][-3:]
        raise BrowserError("скрипт %s не ответил JSON (код %d): %s" % (script, r.returncode, " | ".join(tail)))
    if r.returncode != 0 or data.get("ok") is False:
        raise BrowserError(str(data.get("error") or "код %d" % r.returncode))
    return data


# ── состояние, план, установка ──────────────────────────────────────────────

def target_version() -> str:
    return npx_version() or installed_version() or "latest"


def probe() -> dict:
    try:
        return run("probe.mjs", {}, timeout=PROBE_TIMEOUT)
    except BrowserError as e:
        return {"ok": False, "error": str(e)}


def status(with_probe=True) -> dict:
    nv = node_version()
    st = {"node": nv, "npm": bool(which("npm")), "npxPlaywright": npx_version() if nv else None,
          "installed": installed_version(), "cache": cache_dir(), "browser": None}
    st["target"] = st["npxPlaywright"] or st["installed"] or "latest"
    st["nodeOld"] = bool(nv) and int(nv.split(".")[0]) < NODE_MIN
    st["mismatch"] = bool(st["installed"] and st["npxPlaywright"] and st["installed"] != st["npxPlaywright"])
    if with_probe and nv and st["installed"]:
        st["browser"] = probe()
    st["ready"] = bool(nv and not st["nodeOld"] and st["installed"] and (st["browser"] or {}).get("ok"))
    return st


def plan(st: dict) -> List[List[str]]:
    """Команды, которые поставят модуль; пусто — ставить нечего (или нужен Node)."""
    steps = []
    if not st["node"] or st["nodeOld"] or not st["npm"]:
        return steps
    if not st["installed"] or st["mismatch"]:
        steps.append(["npm", "install", "--prefix", st["cache"], "--no-audit", "--no-fund",
                      "playwright@%s" % st["target"]])
    b = st.get("browser")
    if b is not None and not b.get("ok"):
        steps.append(["node", os.path.join(st["cache"], "node_modules", "playwright", "cli.js"),
                      "install", "chromium"])
    return steps


def _show(cmd: List[str]) -> str:
    return " ".join('"%s"' % p if " " in p else p for p in cmd)


def _execute(cmd: List[str]) -> int:
    exe = which(cmd[0])
    if not exe:
        print("  ! нет программы %s" % cmd[0])
        return 127
    try:
        r = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=INSTALL_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        print("  ! не уложилось в %d с" % INSTALL_TIMEOUT)
        return 124
    if r.returncode:
        for line in [x for x in ((r.stdout or "") + (r.stderr or "")).splitlines() if x.strip()][-5:]:
            print("    " + line)
        print("  ! сбой: код %d. Ничего не удалено; можно повторить." % r.returncode)
    return r.returncode


def _package_json(home: str) -> None:
    os.makedirs(home, exist_ok=True)
    p = os.path.join(home, "package.json")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"name": "aidesign-browser", "private": True,
                       "description": "общий браузерный модуль AI Design"}, f, ensure_ascii=False, indent=2)


def ensure(yes=False) -> int:
    st = status()
    if st["ready"]:
        print("Браузерный модуль готов: playwright %s, браузер %s" % (st["installed"], st["browser"].get("browser")))
        return 0
    if not st["node"] or st["nodeOld"] or not st["npm"]:
        _print_status(st)
        return 1
    steps = plan(st)
    if not yes:
        print("План (ставится в общий кэш скилла, не в проект):")
        for c in steps:
            print("  " + _show(c))
        print("Поставить после «да» человека: python3 browser.py ensure --yes")
        return 1
    for c in steps:
        if c[0] == "npm":
            _package_json(st["cache"])
        print("$ " + _show(c))
        if _execute(c):
            return 1
    st = status()
    _print_status(st)
    return 0 if st["ready"] else 1


def _print_status(st: dict) -> None:
    if not st["node"]:
        print("нет Node.js — браузерного модуля не будет. Поставить: python3 setup.py plan node")
        return
    if st["nodeOld"]:
        print("Node.js %s — старый, нужен %d+: python3 setup.py plan node" % (st["node"], NODE_MIN))
        return
    print("Node.js %s · npx playwright: %s · кэш: %s" % (st["node"], st["npxPlaywright"] or "нет", st["cache"]))
    if not st["installed"]:
        print("пакет playwright в кэше: нет — план: python3 browser.py ensure")
        return
    print("пакет playwright в кэше: %s%s" % (st["installed"], " (у npx — %s, обновится на ensure)"
                                                  % st["npxPlaywright"] if st["mismatch"] else ""))
    b = st["browser"] or {}
    if b.get("ok"):
        print("браузер: %s %s" % (b.get("browser"), b.get("version", "")))
        return
    print("браузер: не запустился — %s" % b.get("error", "?"))
    print("  скачать Chromium этой версии (после «да»): python3 browser.py ensure --yes "
          "(это node …/playwright/cli.js install chromium); или поставить Google Chrome — "
          "он подхватится сам")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Браузерный модуль AI Design")
    sub = p.add_subparsers(dest="cmd")
    d = sub.add_parser("doctor")
    d.add_argument("--json", action="store_true")
    e = sub.add_parser("ensure")
    e.add_argument("--yes", action="store_true")
    e.add_argument("--json", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit as err:
        return 2 if err.code else 0
    if a.cmd == "doctor":
        st = status()
        if a.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            _print_status(st)
        return 0 if st["ready"] else 1
    if a.cmd == "ensure":
        if a.json and not a.yes:
            st = status()
            print(json.dumps({"ready": st["ready"], "plan": plan(st), "status": st}, ensure_ascii=False, indent=2))
            return 0 if st["ready"] else 1
        return ensure(a.yes)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
