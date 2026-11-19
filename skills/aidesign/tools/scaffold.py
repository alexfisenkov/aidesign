#!/usr/bin/env python3
"""Структура проекта для AI Design: чего не хватает и создать недостающее.

    python3 scaffold.py plan  --root . --kind page|site [--json]
    python3 scaffold.py apply --root . --kind page|site --title "…" [--git]

plan ничего не пишет. apply создаёт только отсутствующее и ничего не перезаписывает:
`.gitignore` дописывается строками (ссылку не трогает), `AGENTS.md` (блок aidesign) и
`CLAUDE.md` (`@AGENTS.md`) — только если их нет; при одном своём `CLAUDE.md` AGENTS.md
не создаётся — блок aidesign дописывается в CLAUDE.md. В готовом сайте (есть .html или package.json)
раскладка — index.html, assets/, pages/ — только предлагается (`propose`): адреса
страниц и ссылки — часть того, что работает, переносят их только с согласия.
--git: если репозитория нет — `git init` и коммит «До AI Design» до любых правок.
Коды выхода: 0 — хорошо, 1 — git не смог закоммитить, 2 — ошибка ввода.
"""

import argparse
import html
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import List

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Путь, папка ли, что в нём, относится ли к раскладке сайта (её в готовом сайте не трогаем).
_COMMON = [
    ("index.html", False, "главная страница", True),
    ("assets/css", True, "стили сайта; токены — в design-system/", True),
    ("assets/js", True, "скрипты", True),
    ("assets/img", True, "картинки (WebP/AVIF, с размерами)", True),
    ("assets/video", True, "видео (MP4 H.264 + WebM, постер)", True),
    ("assets/fonts", True, "свои шрифты", True),
    ("design-system", True, "единственный источник стиля: tokens.css, tokens.json, styleguide.html", False),
    ("DESIGN.md", False, "правила дизайна для любого агента", False),
    ("AGENTS.md", False, "память проекта, блок aidesign", False),
    ("CLAUDE.md", False, "одна строка @AGENTS.md", False),
    ("README.md", False, "что за проект и как открыть", False),
    (".gitignore", False, "служебное — мимо git", False),
]
SCHEMA = {"page": _COMMON, "site": _COMMON + [("pages", True, "остальные страницы сайта", True)]}
# Секреты и пересоздаваемое — мимо git, в том числе мимо коммита «До AI Design».
GITIGNORE = [".env", ".env.*", "!.env.example", "node_modules/", ".aidesign-work/", ".DS_Store"]
SKIP = {".git", ".aidesign-work", ".aispa-work", "node_modules"}


@dataclass
class Item:
    path: str
    exists: bool
    action: str                                            # create | skip | propose | append
    note: str


def is_site(root: str) -> bool:
    """Готовый сайт: есть страница или package.json. Его раскладку не перекладываем."""
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        if any(n.lower().endswith((".html", ".htm")) or n == "package.json" for n in names):
            return True
    return False


def missing_ignores(root: str) -> List[str]:
    try:
        with open(os.path.join(root, ".gitignore"), encoding="utf-8") as f:
            have = {l.strip() for l in f}
    except OSError:
        have = set()
    return [l for l in GITIGNORE if l not in have and l.rstrip("/") not in have]


def _rules():
    """rules.py рядом — одно правило выбора файла памяти и один шаблон блока на ad.py и scaffold.py."""
    spec = importlib.util.spec_from_file_location(
        "aidesign_rules", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RULES = _rules()
own_claude_md = RULES.own_claude_md


def plan(root: str, kind: str) -> List[Item]:
    site = is_site(root)
    out = []
    for path, _is_dir, note, layout in SCHEMA[kind]:
        exists = os.path.lexists(os.path.join(root, *path.split("/")))
        if path == ".gitignore" and os.path.islink(os.path.join(root, ".gitignore")):
            action, note = "skip", "ссылка — не трогаю; строки %s допишите сами" % " ".join(GITIGNORE)
        elif path == ".gitignore" and exists:
            action = "append" if missing_ignores(root) else "skip"
        elif path == "AGENTS.md" and own_claude_md(root):
            action, note = "skip", "есть свой CLAUDE.md — блок aidesign допишется в него, AGENTS.md не нужен"
        elif exists:
            action = "skip"
        elif site and layout:
            action = "propose"
        else:
            action = "create"
        out.append(Item(path, exists, action, note))
    return out


def page_html(title: str) -> str:
    return ("<!doctype html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>%s</title>\n"
            "<link rel=\"stylesheet\" href=\"design-system/tokens.css\">\n</head>\n<body>\n<main>\n"
            "<h1>%s</h1>\n<p>[Первый экран — впиши]</p>\n</main>\n</body>\n</html>\n") % ((html.escape(title),) * 2)


def file_text(path: str, title: str, root: str = ".") -> str:
    return {
        "index.html": page_html(title),
        "DESIGN.md": "# Правила дизайна — %s\n\nНаправление ещё не выбрано. Файл заполнит AI Design после выбора "
                     "превью; стиль берётся только из `design-system/`.\n" % title,
        "AGENTS.md": "# %s\n\n%s" % (title, RULES.new_block(RULES.now_block(
            RULES.now_lines(root, None, "структура проекта создана")))),
        "CLAUDE.md": "@AGENTS.md\n",
        "README.md": "# %s\n\nОткрыть: `index.html` в браузере. Правила дизайна — `DESIGN.md`.\n" % title,
        "design-system/README.md": "# Дизайн-система\n\nЗдесь живёт стиль проекта: `tokens.css` — источник, "
                                   "`tokens.json` выводится из него, `styleguide.html` — витрина. Сайт подключает "
                                   "`design-system/tokens.css` и своих значений цвета не держит.\n",
    }.get(path, "")


def git(root: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def git_first_commit(root: str) -> str:
    if os.path.exists(os.path.join(root, ".git")):
        return "git уже есть — коммит «До AI Design» не нужен"
    try:
        if git(root, "init").returncode:
            return "! git init не прошёл"
    except OSError:
        return "! git не установлен — python3 setup.py plan git"
    git(root, "add", "-A")
    r = git(root, "commit", "--allow-empty", "-m", "До AI Design")
    if r.returncode:
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
        return "! коммит не прошёл: %s (нужны git config user.name и user.email)" % tail[0]
    return "git init и коммит «До AI Design» — состояние до правок сохранено"


def ensure_gitignore(root: str) -> List[str]:
    """Дописывает недостающие строки, ничего не перезаписывая. Идёт первым: до git add.
    `.gitignore`-ссылка на запись не открывается: дописали бы чужой файл за пределами проекта."""
    full = os.path.join(root, ".gitignore")
    if os.path.islink(full):
        return ["! .gitignore — ссылка, не трогаю: допишите сами строки %s" % " ".join(GITIGNORE)]
    lines = missing_ignores(root)
    if not lines:
        return []
    existed = os.path.exists(full)
    with open(full, "a+", encoding="utf-8") as f:
        f.seek(0)
        text = f.read()
        f.write(("" if not text or text.endswith("\n") else "\n") + "\n".join(lines) + "\n")
    return [".gitignore дописан" if existed else "создан .gitignore"]


def apply(root: str, kind: str, project_title: str, use_git: bool = False) -> List[str]:
    notes = ensure_gitignore(root)
    if use_git and any(n.startswith("! .gitignore") for n in notes):
        notes.append("! git: первый коммит не сделан — без своего .gitignore в него ушли бы секреты и копии")
    elif use_git:
        notes.append(git_first_commit(root))
    for item in plan(root, kind):
        full = os.path.join(root, *item.path.split("/"))
        if item.action != "create" or item.path == ".gitignore":
            continue
        elif any(item.path == p and d for p, d, _, _ in SCHEMA[kind]):
            os.makedirs(full, exist_ok=True)
            readme = os.path.join(full, "README.md") if item.path == "design-system" else os.path.join(full, ".gitkeep")
            if not os.path.exists(readme):
                with open(readme, "w", encoding="utf-8") as f:
                    f.write(file_text("design-system/README.md", project_title) if item.path == "design-system" else "")
            notes.append("создана папка %s/" % item.path)
        else:
            with open(full, "x", encoding="utf-8") as f:     # «x» — никогда не перезаписать
                f.write(file_text(item.path, project_title, root))
            notes.append("создан %s" % item.path)
    return notes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Структура проекта (AI Design)")
    sub = p.add_subparsers(dest="cmd")
    for name in ("plan", "apply"):
        x = sub.add_parser(name)
        x.add_argument("--root", default=".")
        x.add_argument("--kind", choices=sorted(SCHEMA), required=True)
        if name == "plan":
            x.add_argument("--json", action="store_true")
        else:
            x.add_argument("--title", required=True)
            x.add_argument("--git", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if not a.cmd or not os.path.isdir(a.root):
        print("Ошибка: нужна команда plan|apply и существующая папка --root", file=sys.stderr)
        return 2
    root = os.path.abspath(a.root)
    if a.cmd == "plan":
        items = plan(root, a.kind)
        if a.json:
            print(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2))
        else:
            words = {"create": "создам", "skip": "есть", "propose": "предлагаю, с согласия", "append": "допишу"}
            for i in items:
                print("%-16s %-22s %s" % (i.path, words[i.action], i.note))
        return 0
    notes = apply(root, a.kind, a.title, a.git)
    for n in notes:
        print(n if n.startswith("!") else "· " + n)
    return 1 if any(n.startswith(("! коммит", "! git init", "! git:")) for n in notes) else 0


if __name__ == "__main__":
    sys.exit(main())
