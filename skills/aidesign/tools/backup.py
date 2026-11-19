#!/usr/bin/env python3
"""Бэкапы проекта и откат для AI Design: полная копия папкой, суммы, сверка.

    python3 backup.py create --root . --reason "до" [--limit-mb 500] [--force] [--json]
    python3 backup.py list --root . [--json]
    python3 backup.py verify --root . --id ID
    python3 backup.py restore --root . --id ID [--yes] [--json]

Копия — `.aidesign-work/backups/<YYYYMMDD-HHMMSS>-<причина>/files/…` и `manifest.json`
(путь, размер, sha256 каждого файла); после записи каждая копия читается обратно и
сверяется. Не копируется только то, что программа создаёт заново (EXCLUDE).
Откат: сначала копия «перед откатом», потом файлы из копии на место; файлы, которых
в копии не было, не удаляются, а уносятся в `backups/<id>-лишнее/` — и пустые папки,
которых в копии не было (опись помнит папки, `dirs`); в конце — сверка сумм. Без --yes restore только показывает план. Ничего не удаляется никогда.
Коды выхода: 0 — хорошо, 1 — копия больше лимита / сверка не сошлась, 2 — ошибка ввода.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from typing import Dict, List

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

EXCLUDE = {"node_modules", ".git", ".aidesign-work", ".next", ".nuxt", ".cache", "__pycache__", ".venv", "venv"}
BUILT = {"dist", "build"}                                 # только если в корне есть сборка
WORK = ".aidesign-work"
MB = 1024 * 1024


class InputError(Exception):
    """Нет такой копии, неверный корень — ошибка ввода, код 2."""


class TooBig(Exception):
    def __init__(self, size, limit_mb):
        super().__init__("копия заняла бы %s при лимите %s МБ" % (human(size), limit_mb))
        self.size = size


class Broken(Exception):
    """Сверка не сошлась — код 1."""


class Refused(Exception):
    """Писать некуда безопасно (папка копий — ссылка) — код 1."""


@dataclass
class Backup:
    id: str
    path: str
    files: int
    bytes: int


@dataclass
class RestoreResult:
    pre_backup_id: str
    restored: List[str]
    moved_extra: List[str]


def human(n: int) -> str:
    return "%.1f МБ" % (n / MB) if n >= MB else "%d КБ" % max(1, n // 1024) if n >= 1024 else "%d байт" % n


def now() -> dt.datetime:
    return dt.datetime.now().astimezone().replace(microsecond=0)


def backups_dir(root: str) -> str:
    return os.path.join(root, WORK, "backups")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def builds(root: str) -> bool:
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
            return "build" in (json.load(f).get("scripts") or {})
    except (OSError, ValueError, AttributeError):
        return False


def project_files(root: str):
    """(файлы проекта от корня через «/», пропущенное). Ссылки не идут: копия — файлы."""
    skip_top = BUILT if builds(root) else set()
    files, skipped = [], []
    for base, dirs, names in os.walk(root):
        rel_base = os.path.relpath(base, root)
        keep = []
        for d in sorted(dirs):
            rel = d if rel_base == "." else os.path.join(rel_base, d).replace(os.sep, "/")
            if d in EXCLUDE or (rel_base == "." and d in skip_top) or os.path.islink(os.path.join(base, d)):
                skipped.append(rel + "/")
            else:
                keep.append(d)
        dirs[:] = keep
        for n in sorted(names):
            p = os.path.join(base, n)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if os.path.islink(p):
                skipped.append(rel)
            elif os.path.isfile(p):
                files.append(rel)
    return files, skipped


def project_dirs(root: str) -> List[str]:
    """Папки проекта от корня через «/» — по тем же исключениям, что и файлы. Копия
    запоминает их, чтобы откат отличил пустую папку «как было» от появившейся после."""
    skip_top = BUILT if builds(root) else set()
    out = []
    for base, dirs, _ in os.walk(root):
        rel_base = os.path.relpath(base, root)
        dirs[:] = [d for d in sorted(dirs) if not (d in EXCLUDE or (rel_base == "." and d in skip_top)
                                                    or os.path.islink(os.path.join(base, d)))]
        out += [d if rel_base == "." else os.path.join(rel_base, d).replace(os.sep, "/") for d in dirs]
    return out


def copy_dirs(m: dict) -> set:
    """Папки, которые были в копии: из описи, а у старой описи без них — по путям файлов."""
    if isinstance(m.get("dirs"), list):
        return {d for d in m["dirs"] if not unsafe_path(d)}
    out = set()
    for e in m.get("files") or []:
        parts = e["path"].split("/")[:-1]
        out.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    return out


def extra_dirs(root: str, m: dict, extra_files: List[str]) -> List[str]:
    """Верхние папки, которых не было в копии и в которых после выноса лишних файлов
    ничего не останется: их тоже уносим. Папка с исключённым внутри (node_modules,
    ссылка) остаётся на месте — её содержимое откат не трогает."""
    had, gone = copy_dirs(m), set(extra_files)
    new = [d for d in project_dirs(root) if d not in had]
    top = [d for d in new if "/" not in d or d.rsplit("/", 1)[0] in had]
    out = []
    for d in top:
        full, keep = os.path.join(root, *d.split("/")), False
        for base, dirs, names in os.walk(full):
            for n in names + [x for x in dirs if os.path.islink(os.path.join(base, x))]:
                if os.path.relpath(os.path.join(base, n), root).replace(os.sep, "/") not in gone:
                    keep = True
        if not keep:
            out.append(d)
    return sorted(out)


def move_empty_tree(src: str, dst: str) -> None:
    """Папку, где остались только пустые папки, переносит в лишнее: то же дерево там,
    затем пустые папки здесь убираются снизу вверх. Файлов в ней нет — терять нечего."""
    for base, dirs, names in os.walk(src):
        if names or any(os.path.islink(os.path.join(base, d)) for d in dirs):
            raise Broken("в папке %s появились файлы во время отката — она оставлена на месте" % src)
        os.makedirs(os.path.join(dst, os.path.relpath(base, src)), exist_ok=True)
    for base, _, _ in sorted(os.walk(src), key=lambda x: -len(x[0])):
        os.rmdir(base)


def slug(reason: str) -> str:
    s = re.sub(r"[^\w]+", "-", reason.strip().lower(), flags=re.U).strip("-_")
    return s[:40].strip("-") or "копия"


def under_git(root: str) -> bool:
    cur = os.path.abspath(root)
    while True:
        if os.path.lexists(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def ensure_ignored(root: str) -> None:
    """Под git — `.aidesign-work/` в `.gitignore` проекта до первой копии: копии не уходят в коммит.
    Строка дописывается в конец, остальное не трогается; `.gitignore`-ссылка не открывается на запись."""
    if not under_git(root):
        return
    path = os.path.join(root, ".gitignore")
    if os.path.islink(path):
        print("! .gitignore — ссылка, не трогаю: допишите в него строку %s/ сами" % WORK, file=sys.stderr)
        return
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    if any(l.strip().strip("/") == WORK for l in text.splitlines()):
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(("" if not text or text.endswith("\n") else "\n") + WORK + "/\n")


def refuse_links(root: str) -> None:
    for rel in (WORK, os.path.join(WORK, "backups")):
        if os.path.islink(os.path.join(root, rel)):
            raise Refused("%s — ссылка: копия ушла бы за пределы проекта. Сделайте %s обычной папкой"
                          % (rel.replace(os.sep, "/"), rel.replace(os.sep, "/")))


def create(root: str, reason: str, limit_mb: float = 500, force: bool = False) -> Backup:
    root = os.path.abspath(root)
    refuse_links(root)
    ensure_ignored(root)
    files, skipped = project_files(root)
    total = sum(os.path.getsize(os.path.join(root, f)) for f in files)
    if total > limit_mb * MB and not force:
        raise TooBig(total, limit_mb)
    stamp = now()
    bid = "%s-%s" % (stamp.strftime("%Y%m%d-%H%M%S"), slug(reason))
    n = 2
    while os.path.exists(os.path.join(backups_dir(root), bid)):
        bid = "%s-%s-%d" % (stamp.strftime("%Y%m%d-%H%M%S"), slug(reason), n)
        n += 1
    dest = os.path.join(backups_dir(root), bid)
    os.makedirs(dest, exist_ok=True)                      # и у проекта без обычных файлов
    entries, bad = [], []
    for rel in files:
        src = os.path.join(root, *rel.split("/"))
        dst = os.path.join(dest, "files", *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        digest = sha256(src)
        shutil.copy2(src, dst)
        if sha256(dst) != digest:                         # сверка обратным чтением
            bad.append(rel)
        entries.append({"path": rel, "size": os.path.getsize(dst), "sha256": digest})
    manifest = {"id": bid, "reason": reason, "createdAt": stamp.isoformat(), "root": root,
                "files": entries, "dirs": project_dirs(root), "bytes": sum(e["size"] for e in entries),
                "excluded": skipped,
                "status": "BROKEN" if bad else "ok"}
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    if bad:
        raise Broken("копия %s не сошлась с оригиналом: %s" % (bid, ", ".join(bad[:5])))
    return Backup(bid, dest, len(entries), manifest["bytes"])


def unsafe_path(rel) -> bool:
    """Путь из описи, который ведёт за пределы проекта: абсолютный, с диском, с «..» или пустой."""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        return True
    parts = re.split(r"[\\/]", rel)
    return any(p in ("", ".", "..") for p in parts)


def read_manifest(root: str, bid: str) -> dict:
    path = os.path.join(backups_dir(root), bid, "manifest.json")
    if not bid or bid in (".", "..") or "/" in bid or "\\" in bid or not os.path.isfile(path):
        raise InputError("копии %s нет — список: backup.py list" % bid)
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    bad = [e.get("path") if isinstance(e, dict) else e for e in m.get("files") or []
           if not isinstance(e, dict) or unsafe_path(e.get("path"))]
    if bad:
        raise Broken("в описи копии %s путь %s ведёт за пределы проекта — копия не используется, "
                     "ничего не тронуто" % (bid, bad[0]))
    return m


def list_backups(root: str) -> List[dict]:
    out = []
    base = backups_dir(root)
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            m = read_manifest(root, name)
        except Broken:                                    # опись с чужими путями — видна, но не годится
            out.append({"id": name, "reason": None, "createdAt": None, "files": 0, "bytes": 0, "status": "BROKEN"})
            continue
        except (InputError, ValueError, OSError):
            continue
        out.append({"id": m["id"], "reason": m.get("reason"), "createdAt": m.get("createdAt"),
                    "files": len(m.get("files") or []), "bytes": m.get("bytes"), "status": m.get("status", "ok")})
    return out


def verify(root: str, bid: str) -> List[str]:
    m = read_manifest(root, bid)
    problems = ["копия помечена BROKEN"] if m.get("status") == "BROKEN" else []
    for e in m.get("files") or []:
        p = os.path.join(backups_dir(root), bid, "files", *e["path"].split("/"))
        if not os.path.isfile(p):
            problems.append("%s: файла нет в копии" % e["path"])
        elif os.path.getsize(p) != e["size"] or sha256(p) != e["sha256"]:
            problems.append("%s: сумма не сходится" % e["path"])
    return problems


def restore_plan(root: str, bid: str) -> Dict[str, List[str]]:
    m = read_manifest(root, bid)
    want = {e["path"]: e["sha256"] for e in m.get("files") or []}
    have, _ = project_files(root)
    changed = [p for p in want if p in have and sha256(os.path.join(root, *p.split("/"))) != want[p]]
    extra = sorted(set(have) - set(want))
    return {"changed": sorted(changed), "missing": sorted(set(want) - set(have)),
            "extra": extra, "extra_dirs": extra_dirs(root, m, extra)}


def free_place(path: str) -> str:
    n, cand = 2, path
    while os.path.lexists(cand):
        cand = "%s-%d" % (path, n)
        n += 1
    return cand


def move_links_on_path(root: str, rel: str, extra_dir: str) -> List[str]:
    """Ссылку на месте файла или любой папки по пути уносит в лишнее — как ссылку,
    не трогая то, куда она ведёт: запись сквозь ссылку ушла бы за пределы проекта."""
    parts, cur = rel.split("/"), root
    for i, part in enumerate(parts):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            target = free_place(os.path.join(extra_dir, *parts[:i + 1]))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.rename(cur, target)
            return ["/".join(parts[:i + 1])]
        if not os.path.lexists(cur):
            break
    return []


def inside(root: str, path: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base.rstrip(os.sep) + os.sep)


def restore(root: str, bid: str) -> RestoreResult:
    root = os.path.abspath(root)
    problems = verify(root, bid)
    if problems:
        raise Broken("копия %s повреждена, откат не начат: %s" % (bid, "; ".join(problems[:5])))
    pre = create(root, "перед-откатом", force=True)
    plan = restore_plan(root, bid)
    extra_dir = free_place(os.path.join(backups_dir(root), bid + "-лишнее"))
    for rel in plan["extra"]:                             # не удаляем — уносим
        dst = os.path.join(extra_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(os.path.join(root, *rel.split("/")), dst)
    moved_dirs = []
    for rel in plan["extra_dirs"]:                        # пустые папки, которых не было в копии
        src = os.path.join(root, *rel.split("/"))
        if os.path.isdir(src) and not os.path.islink(src) and inside(root, src):
            move_empty_tree(src, os.path.join(extra_dir, *rel.split("/")))
            moved_dirs.append(rel + "/")
    restored, links = [], []
    for rel in plan["changed"] + plan["missing"]:
        src = os.path.join(backups_dir(root), bid, "files", *rel.split("/"))
        dst = os.path.join(root, *rel.split("/"))
        links += move_links_on_path(root, rel, extra_dir)
        if not inside(root, dst):                         # «..» в manifest или ссылка, которую не убрать
            raise Broken("путь %s ведёт за пределы проекта — откат остановлен. Копия текущего "
                         "состояния — %s" % (rel, pre.id))
        if os.path.isdir(dst):                            # на месте файла выросла папка
            target = os.path.join(extra_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(dst, free_place(target))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not inside(root, os.path.dirname(dst)):
            raise Broken("папка для %s оказалась вне проекта — откат остановлен" % rel)
        shutil.copy2(src, dst)
        restored.append(rel)
    left = restore_plan(root, bid)
    if left["changed"] or left["missing"]:
        raise Broken("после отката не сошлись: %s. Копия текущего состояния — %s"
                     % (", ".join((left["changed"] + left["missing"])[:5]), pre.id))
    return RestoreResult(pre.id, sorted(restored), sorted(plan["extra"] + links + moved_dirs))


# ── командная строка ────────────────────────────────────────────────────────

def say(data, as_json: bool, text: str) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2) if as_json else text)


def run(a) -> int:
    root = os.path.abspath(a.root)
    if not os.path.isdir(root):
        raise InputError("папки %s нет" % a.root)
    if a.cmd == "create":
        b = create(root, a.reason, a.limit_mb, a.force)
        say(asdict(b), a.json, "Копия %s: файлов %d, %s, сверена.\nНа панель: python3 .aidesign-work/ad.py "
            "backup add --id %s --reason \"%s\" --bytes %d" % (b.id, b.files, human(b.bytes), b.id, a.reason, b.bytes))
    elif a.cmd == "list":
        items = list_backups(root)
        say(items, a.json, "\n".join("%s · %s · файлов %d · %s%s" % (x["id"], x["reason"], x["files"], human(x["bytes"] or 0),
                                     "" if x["status"] == "ok" else " · " + x["status"]) for x in items) or "Копий нет.")
    elif a.cmd == "verify":
        problems = verify(root, a.id)
        say(problems, a.json, "\n".join(problems) if problems else "Копия %s цела." % a.id)
        return 1 if problems else 0
    elif a.cmd == "restore" and not a.yes:
        plan = restore_plan(root, a.id)
        lines = ["План отката к %s (ничего не сделано):" % a.id,
                 "- сначала копия текущего состояния «перед откатом»",
                 "- вернутся из копии: %d (изменены: %s; пропали: %s)" % (
                     len(plan["changed"]) + len(plan["missing"]), ", ".join(plan["changed"]) or "—",
                     ", ".join(plan["missing"]) or "—"),
                 "- уйдут в backups/%s-лишнее/ (не удаляются): %s" % (
                     a.id, ", ".join(plan["extra"] + [d + "/" for d in plan["extra_dirs"]]) or "—"),
                 "Откатить: python3 .aidesign-work/backup.py restore --id %s --yes" % a.id]
        say(plan, a.json, "\n".join(lines))
    elif a.cmd == "restore":
        r = restore(root, a.id)
        say(asdict(r), a.json, "Откат к %s сделан, суммы сошлись. Вернулись: %d, унесены в %s-лишнее: %d.\n"
            "Копия перед откатом: %s" % (a.id, len(r.restored), a.id, len(r.moved_extra), r.pre_backup_id))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Бэкапы проекта и откат (AI Design)")
    sub = p.add_subparsers(dest="cmd")
    for name in ("create", "list", "verify", "restore"):
        x = sub.add_parser(name)
        x.add_argument("--root", "--src", dest="root", default=".")
        x.add_argument("--json", action="store_true")
        if name == "create":
            x.add_argument("--reason", required=True)
            x.add_argument("--limit-mb", type=float, default=500)
            x.add_argument("--force", action="store_true")
        if name in ("verify", "restore"):
            x.add_argument("--id", required=True)
        if name == "restore":
            x.add_argument("--yes", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if not a.cmd:
        p.print_help()
        return 2
    try:
        return run(a)
    except InputError as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 2
    except TooBig as e:
        print("Копия не сделана: %s. Сделать всё равно: добавьте --force (спросите человека)." % e)
        return 1
    except Broken as e:
        print("Ошибка сверки: %s" % e)
        return 1
    except Refused as e:
        print("Копия не сделана: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
