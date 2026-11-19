#!/usr/bin/env python3
"""Оснащение компьютера для AI Design: что стоит, чего нет и как поставить.

    python3 setup.py doctor [--need video,check,figma] [--os mac|windows|linux] [--json]
    python3 setup.py plan <программы…> [--os mac|windows|linux] [--pkg brew|winget|apt|dnf|pacman] [--host claude|codex] [--json]
    python3 setup.py install <программы…> --yes

Программы: python, git, node, playwright, ffmpeg, webp, figma.
doctor только смотрит; plan только печатает; install ставит официальными командами
по одной и только с --yes, у каждой — ограничение по времени. Команда, которой нужен
пароль администратора (sudo, установка Homebrew, установщик Windows с запросом прав),
не запускается: человек получает её строкой «выполните в своём Терминале: …», пароль
в чат не просится. На Mac без Homebrew первая такая строка — установка Homebrew.
Node.js старее 22 — «нужно обновить»: Playwright и nodejs.org поддерживают линии LTS от 22.
Коды выхода: 0 — всё нужное есть / всё поставлено, 1 — чего-то нет / осталось
человеку / сбой, 2 — ошибка ввода. Только стандартная библиотека Python 3.9+.
Для тестов: AIDESIGN_SETUP_PATH подменяет PATH для doctor и plan (install с ней
отказывает — ставить можно только то, что видит настоящий PATH);
AIDESIGN_SETUP_TIMEOUT — предел одного шага установки в секундах (по умолчанию 1800).
"""

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

OSES = ("mac", "windows", "linux")
PKGS = ("brew", "winget", "apt", "dnf", "pacman")
DEFAULT_PKG = {"mac": "brew", "windows": "winget", "linux": "apt"}
FIGMA_URL = "https://mcp.figma.com/mcp"
HOMEBREW_LINE = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
NEED_WORDS = {"always": "всегда", "build": "почти всегда", "check": "для проверки", "video": "для видео",
              "optional": "по желанию"}
NODE_MIN = 22                                              # самая старая поддерживаемая линия LTS (nodejs.org, Playwright)
NODE_UPDATE = "нужно обновить: свежая LTS с https://nodejs.org/en/download"
STEP_TIMEOUT = 1800                                        # секунд на один шаг установки
# winget без согласий спрашивает их и ждёт клавишу (learn.microsoft.com/windows/package-manager/winget/install)
WINGET_AGREE = ["--accept-source-agreements", "--accept-package-agreements"]


def _winget(pkg_id):
    return ["winget", "install", "--id", pkg_id, "-e", "--source", "winget"] + WINGET_AGREE


@dataclass
class Tool:
    id: str
    title: str
    need: str
    why: str
    probe: List[List[str]]
    version_re: str
    install: Dict[str, List[List[str]]]                # ключ — пакетный менеджер
    needs_admin: Dict[str, bool] = field(default_factory=dict)
    manual_hint: Dict[str, str] = field(default_factory=dict)


@dataclass
class Status:
    id: str
    need: str
    present: Optional[bool]
    version: Optional[str]
    hint: str


@dataclass
class Step:
    id: str
    cmd: List[str]
    needs_admin: bool
    manual: str = ""                                   # строка для человека вместо команды


def _sudo(*cmd):
    return ["sudo"] + list(cmd)


TOOLS = [
    Tool("python", "Python 3.9+", "always", "панель, проверки, бэкапы",
         [["python3", "--version"], ["python", "--version"], ["py", "-3", "--version"]], r"(\d+\.\d+(?:\.\d+)?)",
         {"brew": [["brew", "install", "python"]],
          "winget": [_winget("Python.Python.3.12")],
          "apt": [_sudo("apt-get", "install", "-y", "python3")], "dnf": [_sudo("dnf", "install", "-y", "python3")],
          "pacman": [_sudo("pacman", "-S", "--needed", "--noconfirm", "python")]},
         {"apt": True, "dnf": True, "pacman": True},
         {"mac": "xcode-select --install (Python и git вместе) или Homebrew с brew.sh",
          "windows": "python.org/downloads — установщик, галочка «Add python.exe to PATH»",
          "linux": "пакет python3 из пакетного менеджера системы"}),
    Tool("git", "git", "always", "история и откат", [["git", "--version"]], r"(\d+\.\d+(?:\.\d+)?)",
         {"brew": [["brew", "install", "git"]],
          "winget": [_winget("Git.Git")],
          "apt": [_sudo("apt-get", "install", "-y", "git")], "dnf": [_sudo("dnf", "install", "-y", "git")],
          "pacman": [_sudo("pacman", "-S", "--needed", "--noconfirm", "git")]},
         {"winget": True, "apt": True, "dnf": True, "pacman": True},
         {"mac": "xcode-select --install", "windows": "git-scm.com/downloads/win", "linux": "пакет git"}),
    Tool("node", "Node.js LTS (npm, npx)", "build", "установка скиллов, фреймворки, Playwright",
         [["node", "--version"]], r"v?(\d+\.\d+\.\d+)",
         {"brew": [["brew", "install", "node"]],
          "winget": [_winget("OpenJS.NodeJS.LTS")],
          "apt": [_sudo("apt-get", "install", "-y", "nodejs", "npm")],
          "dnf": [_sudo("dnf", "install", "-y", "nodejs", "npm")],
          "pacman": [_sudo("pacman", "-S", "--needed", "--noconfirm", "nodejs", "npm")]},
         {"winget": True, "apt": True, "dnf": True, "pacman": True},
         {"mac": "установщик LTS с nodejs.org", "windows": "установщик LTS с nodejs.org",
          "linux": "nodejs.org/en/download — свежая LTS, если в системе старая"}),
    Tool("playwright", "Chromium через Playwright", "check", "снимки 390 и 1280, проверка в браузере",
         [], "", {}, {}, {"mac": "сначала Node.js", "windows": "сначала Node.js", "linux": "сначала Node.js"}),
    Tool("ffmpeg", "ffmpeg", "video", "сжатие видео, постер, кадры, WebP/AVIF",
         [["ffmpeg", "-version"]], r"version\s+n?(\d+(?:\.\d+)*)",
         {"brew": [["brew", "install", "ffmpeg"]],
          "winget": [_winget("Gyan.FFmpeg")],
          "apt": [_sudo("apt-get", "install", "-y", "ffmpeg")], "dnf": [_sudo("dnf", "install", "-y", "ffmpeg-free")],
          "pacman": [_sudo("pacman", "-S", "--needed", "--noconfirm", "ffmpeg")]},
         {"apt": True, "dnf": True, "pacman": True},
         {"mac": "ffmpeg.org/download.html", "windows": "ffmpeg.org/download.html — сборки gyan.dev",
          "linux": "пакет ffmpeg (в Fedora — ffmpeg-free или RPM Fusion)"}),
    # cwebp — запасной путь WebP для media.py prep, когда ffmpeg собран без libwebp (так у Homebrew).
    Tool("webp", "WebP (cwebp)", "optional", "картинки WebP, если в ffmpeg нет libwebp",
         [["cwebp", "-version"]], r"(\d+\.\d+(?:\.\d+)?)",
         {"brew": [["brew", "install", "webp"]],
          "winget": [_winget("Google.Libwebp")],
          "apt": [_sudo("apt-get", "install", "-y", "webp")], "dnf": [_sudo("dnf", "install", "-y", "libwebp-tools")],
          "pacman": [_sudo("pacman", "-S", "--needed", "--noconfirm", "libwebp")]},
         {"apt": True, "dnf": True, "pacman": True},
         {"mac": "developers.google.com/speed/webp/download", "windows": "developers.google.com/speed/webp/download",
          "linux": "пакет webp (Fedora — libwebp-tools, Arch — libwebp)"}),
    Tool("figma", "Figma MCP", "optional", "проект в Figma, только по желанию", [], "", {}, {},
         {"mac": "подключение видит агент, не этот скрипт", "windows": "подключение видит агент, не этот скрипт",
          "linux": "подключение видит агент, не этот скрипт"}),
]
BY_ID = {t.id: t for t in TOOLS}
PLAYWRIGHT = [["npx", "playwright", "install", "chromium"]]
PLAYWRIGHT_DEPS = ["sudo", "npx", "playwright", "install-deps", "chromium"]
FIGMA = {"claude": [["claude", "mcp", "add", "--transport", "http", "figma", FIGMA_URL]],
         "codex": [["codex", "mcp", "add", "figma", "--url", FIGMA_URL], ["codex", "mcp", "login", "figma"]]}


# ── где мы ──────────────────────────────────────────────────────────────────

def search_path() -> str:
    return os.environ.get("AIDESIGN_SETUP_PATH") or os.environ.get("PATH", "")


def which(name: str) -> Optional[str]:
    return shutil.which(name, path=search_path())


def detect_os() -> str:
    s = platform.system().lower()
    return "mac" if s == "darwin" else "windows" if s.startswith("win") else "linux"


def detect_pkg(os_id: str) -> Optional[str]:
    order = {"mac": ["brew"], "windows": ["winget"], "linux": ["apt-get", "dnf", "pacman"]}[os_id]
    for prog in order:
        if which(prog):
            return "apt" if prog == "apt-get" else prog
    return None


# ── проба ───────────────────────────────────────────────────────────────────

def _output(cmd: List[str]) -> Optional[str]:
    exe = which(cmd[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, timeout=15,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or "") + (r.stderr or "") if r.returncode == 0 else None


def browsers_dir() -> str:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    home = os.path.expanduser("~")
    if detect_os() == "mac":
        return os.path.join(home, "Library", "Caches", "ms-playwright")
    if detect_os() == "windows":
        return os.path.join(os.environ.get("LOCALAPPDATA", home), "ms-playwright")
    return os.path.join(home, ".cache", "ms-playwright")


def playwright_package() -> Optional[str]:
    """Версия пакета Playwright в общем кэше скилла (browser.py cache_dir), без запуска npx."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser.py")
    try:
        spec = importlib.util.spec_from_file_location("aidesign_browser_for_setup", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.installed_version()
    except (OSError, ImportError, AttributeError, SyntaxError):
        return None


def probe(tool: Tool):
    """(есть ли, версия). Figma — None: подключение MCP видит только агент."""
    if tool.id == "figma":
        return None, None
    if tool.id == "playwright":
        try:
            found = sorted(d for d in os.listdir(browsers_dir()) if re.match(r"chromium-\d+$", d))
        except OSError:
            found = []
        if not found:
            return False, None
        build = "сборка Chromium %s" % found[-1].split("-", 1)[1]
        pkg = playwright_package()
        return True, "%s (%s)" % (pkg, build) if pkg else build
    for cmd in tool.probe:
        out = _output(cmd)
        m = re.search(tool.version_re, out or "")
        if m:
            if tool.id == "python" and tuple(int(x) for x in m.group(1).split(".")[:2]) < (3, 9):
                continue
            return True, m.group(1)
    if tool.id == "python":                                 # скрипт уже идёт под Python 3.9+
        return True, "%d.%d.%d" % sys.version_info[:3]
    return False, None


def too_old(tool: Tool, version: Optional[str]) -> bool:
    return tool.id == "node" and bool(version) and int(version.split(".")[0]) < NODE_MIN


def doctor(needs=frozenset(), os_id=None) -> List[Status]:
    os_id = os_id or detect_os()
    pkg = detect_pkg(os_id)
    out = []
    for t in TOOLS:
        present, version = probe(t)
        if present and too_old(t, version):
            out.append(Status(t.id, t.need, False, version, NODE_UPDATE))
            continue
        hint = "" if present else human_text(steps_for([t.id], os_id, pkg))
        out.append(Status(t.id, t.need, present, version, hint))
    return out


def required(status: Status, needs) -> bool:
    return status.need == "always" or status.need in needs or status.id in needs


# ── план и установка ────────────────────────────────────────────────────────

def plan(ids, os_id=None, pkg=None, host="claude") -> List[Step]:
    """Команды без установки. С --os — для любой системы, пакетный менеджер по умолчанию;
    без --os — для этого компьютера, по тому, что на нём есть."""
    forced = os_id is not None
    os_id = os_id or detect_os()
    if pkg is None:
        pkg = DEFAULT_PKG[os_id] if forced else detect_pkg(os_id)
    return steps_for(ids, os_id, pkg, host)


def steps_for(ids, os_id: str, pkg: Optional[str], host="claude") -> List[Step]:
    """Шаги для системы os_id с пакетным менеджером pkg (None — его нет на компьютере)."""
    steps = []
    if os_id == "mac" and pkg is None and set(ids) - {"figma", "playwright"}:
        steps.append(Step("homebrew", [], True, HOMEBREW_LINE))
        pkg = "brew"
    for tid in ids:
        t = BY_ID[tid]
        if tid == "figma":
            steps += [Step(tid, c, False, "войдите в Figma в браузере: " + " ".join(c) if c[-2:] == ["login", "figma"] else "")
                      for c in FIGMA[host]]
        elif tid == "playwright":
            steps += [Step(tid, c, False) for c in PLAYWRIGHT]
            if os_id == "linux":
                steps.append(Step(tid, PLAYWRIGHT_DEPS, True))
        elif pkg in t.install:
            steps += [Step(tid, c, t.needs_admin.get(pkg, False)) for c in t.install[pkg]]
        else:
            steps.append(Step(tid, [], False, t.manual_hint.get(os_id, "")))
    return steps


def show(step: Step) -> str:
    if step.manual and not step.cmd:
        return step.manual
    return " ".join('"%s"' % p if " " in p else p for p in step.cmd)


def human_text(steps: List[Step]) -> str:
    return " ; ".join(show(s) + (" (пароль администратора — в своём Терминале)" if s.needs_admin else "")
                      for s in steps)


def step_timeout() -> float:
    try:
        return float(os.environ.get("AIDESIGN_SETUP_TIMEOUT") or STEP_TIMEOUT)
    except ValueError:
        return STEP_TIMEOUT


def _execute(cmd: List[str], limit: float):
    """(код, вывод); код None — не уложилась во время. Ввод закрыт: шаг не ждёт клавишу.
    Своя группа процессов — по истечении времени гасятся и дочерние (brew, установщики)."""
    posix = os.name != "nt"
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", start_new_session=posix)
    try:
        out, _ = p.communicate(timeout=limit)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL) if posix else p.kill()
        except OSError:
            pass
        try:
            out, _ = p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = ""
        return None, out or ""


def run_step(step: Step) -> int:
    exe = which(step.cmd[0])
    if not exe:
        print("  ! команды %s нет — сначала поставьте её (setup.py doctor покажет как)" % step.cmd[0])
        return 127
    limit = step_timeout()
    code, out = _execute([exe] + step.cmd[1:], limit)
    tail = [l for l in out.splitlines() if l.strip()][-5:]
    if code is None:
        print("  ! сбой: команда не уложилась в %d с и остановлена. Последние строки:" % limit)
    elif code:
        print("  ! сбой: код %d. Последние строки:" % code)
    if code is None or code:
        for line in tail:
            print("    " + line)
        print("  Дальше на выбор: повторить; поставить самому по подсказке; пропустить. Ничего не удалено.")
        return 124 if code is None else code
    print("  готово")
    return 0


def install(ids, os_id=None, pkg=None, host="claude") -> int:
    """Ставит на этом компьютере: пакетный менеджер — названный или тот, что найден."""
    os_id = os_id or detect_os()
    steps = steps_for(ids, os_id, pkg or detect_pkg(os_id), host)
    for i, step in enumerate(steps):
        if step.needs_admin or step.manual:
            rest = steps[i:]
            for s in rest:
                if s.needs_admin and (s.cmd or s.id == "homebrew"):
                    print("выполните в своём Терминале: %s" % show(s))
                elif s.needs_admin or (s.manual and not s.cmd):
                    print("сделайте сами: %s" % show(s))
                elif s.manual:
                    print(s.manual)
            later = sorted({s.id for s in rest if not s.needs_admin and not s.manual and s.cmd})
            if later:
                print("после этого: python3 setup.py install %s --yes" % " ".join(later))
            print("Скажите «готово» — проверю снова: python3 setup.py doctor")
            return 1
        print("$ " + show(step))
        if run_step(step):
            return 1
    print("Всё поставлено. Проверка: python3 setup.py doctor")
    return 0


# ── командная строка ────────────────────────────────────────────────────────

def print_table(rows: List[Status], needs) -> None:
    if any(s.present is False and s.hint.startswith(HOMEBREW_LINE) for s in rows):
        print("выполните в своём Терминале: %s — сначала Homebrew, через него ставится остальное; "
              "пароль вводите там, не в чат" % HOMEBREW_LINE)
    print("%-11s %-14s %-16s %s" % ("программа", "нужна", "есть", "как поставить"))
    for s in rows:
        if s.present is False and s.version:
            have = "%s — нужно обновить" % s.version
        else:
            have = "есть %s" % (s.version or "") if s.present else ("нет" if s.present is False else "видит агент")
        need = NEED_WORDS.get(s.need, s.need) + (" ✱" if required(s, needs) else "")
        print("%-11s %-14s %-16s %s" % (s.id, need, have.strip(), s.hint if s.present is False else ""))
    print("✱ — нужно этому прогону")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Оснащение компьютера для AI Design")
    sub = p.add_subparsers(dest="cmd")
    d = sub.add_parser("doctor")
    d.add_argument("--need", default="")
    d.add_argument("--os", dest="os_id", choices=OSES)
    d.add_argument("--json", action="store_true")
    for name in ("plan", "install"):
        x = sub.add_parser(name)
        x.add_argument("ids", nargs="+")
        x.add_argument("--os", dest="os_id", choices=OSES)
        x.add_argument("--pkg", choices=PKGS)
        x.add_argument("--host", choices=sorted(FIGMA), default="claude")
        x.add_argument("--json", action="store_true")
        x.add_argument("--yes", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.cmd == "doctor":
        needs = {w.strip() for w in a.need.split(",") if w.strip()}
        rows = doctor(needs, a.os_id)
        if a.json:
            print(json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2))
        else:
            print_table(rows, needs)
        return 1 if any(r.present is False and required(r, needs) for r in rows) else 0
    if a.cmd not in ("plan", "install"):
        p.print_help()
        return 2
    bad = [i for i in a.ids if i not in BY_ID]
    if bad:
        print("Ошибка: неизвестная программа %s. Есть: %s" % (", ".join(bad), ", ".join(BY_ID)), file=sys.stderr)
        return 2
    if a.cmd == "install" and os.environ.get("AIDESIGN_SETUP_PATH"):
        print("Ошибка: AIDESIGN_SETUP_PATH — подмена для проверки (doctor, plan); install с ней не ставит "
              "ничего. Уберите переменную и повторите.", file=sys.stderr)
        return 2
    if a.cmd == "install" and a.yes:
        return install(a.ids, a.os_id, a.pkg, a.host)
    steps = plan(a.ids, a.os_id, a.pkg, a.host)
    if a.json:
        print(json.dumps([asdict(s) for s in steps], ensure_ascii=False, indent=2))
        return 0
    for s in steps:
        print(("[администратор] " if s.needs_admin else "") + show(s))
    if a.cmd == "install":
        print("Это план. Поставить: python3 setup.py install %s --yes" % " ".join(a.ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
