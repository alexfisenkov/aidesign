#!/usr/bin/env python3
"""Чистая выгрузка репозитория AI Design для публикации.

Запуск из корня репозитория:
    python3 tools/public-export.py [--out ПАПКА] [--repo КОРЕНЬ]

Берёт файлы из `git ls-files` (в их текущем виде на диске), пропускает рабочие
`.aispa-work/` и `БРИФ.md`, копирует в новую или пустую папку (по умолчанию —
временная) и проверяет выгрузку: пути домашней папки Мака, адреса почты кроме
example.*, токены по известным образцам, слова об основе семейства вне LICENSE и
последней строки README. Печатает путь выгрузки. Новые файлы, которых ещё нет в
git (и нет в .gitignore), не выгружаются — каждый назван строкой «Не в git, не
выгружено: …»: закоммить их до выгрузки для выпуска. На код выхода это не влияет.

Выход: 0 — выгрузка чистая; 1 — есть находки (список в stdout, папка остаётся
для разбора); 2 — ошибка ввода (не git, папка не пуста).
Только стандартная библиотека Python 3.9+.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

EXCLUDE_DIRS = (".aispa-work/",)
EXCLUDE_FILES = ("БРИФ.md",)
README_FILES = ("README.md", "README.ru.md")
BASE_ALLOWED = ("LICENSE",)

# Образцы собраны по частям, чтобы скрипт и тесты не находили сами себя.
MAC_PATH = "/Use" + "rs/"
BASE_WORDS = re.compile("auto" + "pilot|nick" + r"\s+vels", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
HARMLESS_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
SECRETS = [
    ("ключ sk-", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("токен GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("ключ AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("ключ Google", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("токен Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("токен Telegram", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("закрытый ключ", re.compile("-----BEGIN [A-Z ]*PRIVATE" + " KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]


def tracked_files(repo):
    """Отслеживаемые git файлы без рабочих: относительные пути через «/»."""
    r = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=repo,
                       capture_output=True, check=True)
    names = [n for n in r.stdout.decode("utf-8").split("\0") if n]
    return [n for n in names
            if not n.startswith(EXCLUDE_DIRS) and os.path.basename(n) not in EXCLUDE_FILES]


def untracked_files(repo):
    """Файлы, которых нет в git и которые не в .gitignore: в выгрузку они не попадут."""
    r = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z", "--others", "--exclude-standard"],
                       cwd=repo, capture_output=True, check=True)
    names = [n for n in r.stdout.decode("utf-8").split("\0") if n]
    return sorted(n for n in names
                  if not n.startswith(EXCLUDE_DIRS) and os.path.basename(n) not in EXCLUDE_FILES)


def scan_text(rel, text):
    """Находки в одном файле: список строк «файл: что не так»."""
    found = []
    if MAC_PATH in text:
        found.append("%s: путь домашней папки Мака" % rel)
    for address in EMAIL.findall(text):
        if address.rsplit("@", 1)[1].lower() not in HARMLESS_EMAIL_DOMAINS:
            found.append("%s: адрес почты" % rel)
            break
    for label, pattern in SECRETS:
        if pattern.search(text):
            found.append("%s: похоже на %s" % (rel, label))
    body = text
    if rel in README_FILES:
        body = "\n".join(text.rstrip().splitlines()[:-1])
    if rel not in BASE_ALLOWED and BASE_WORDS.search(body):
        found.append("%s: имя основы вне LICENSE и последней строки README" % rel)
    return found


def scan_tree(root):
    """Находки по всем текстовым файлам папки; бинарные пропускаются."""
    found = []
    for base, _, names in os.walk(root):
        for name in sorted(names):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            found += scan_text(rel, text)
    return found


def prepare_out(out):
    if out is None:
        return tempfile.mkdtemp(prefix="aidesign-public-")
    if os.path.exists(out) and (not os.path.isdir(out) or os.listdir(out)):
        raise ValueError("папка выгрузки не пуста: %s" % out)
    os.makedirs(out, exist_ok=True)
    return out


def export(repo, out):
    files = tracked_files(repo)
    for rel in files:
        src = os.path.join(repo, *rel.split("/"))
        if not os.path.isfile(src):
            continue                                   # удалён на диске, но ещё в индексе
        dst = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return scan_tree(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Чистая выгрузка AI Design для публикации")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--out", default=None, help="новая или пустая папка; по умолчанию временная")
    args = ap.parse_args(argv)
    try:
        out = prepare_out(args.out)
        found = export(os.path.abspath(args.repo), out)
        missing = untracked_files(os.path.abspath(args.repo))
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 2
    for line in found:
        print(line)
    for rel in missing:
        print("Не в git, не выгружено: %s" % rel)
    print("Выгрузка: %s" % out)
    print("Находок: %d" % len(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
