#!/usr/bin/env python3
"""Правила проекта для любого следующего агента: блок aidesign в AGENTS.md / CLAUDE.md.

Не запускается сам: его зовут ad.py (после каждого события, которое меняет проект) и
scaffold.py (какой файл памяти и чем его начать). Лежит рядом с ними в .aidesign-work/.

Делит блок на две части. Подраздел «Сейчас» между метками aidesign:now — факты прогона
(направление, дизайн-система, последние копии и команда отката, Figma, оснащение, прогон);
его переписывает только ad.py. Остальное в блоке пишет агент по phases/6-handoff.md, и
отсюда оно не меняется. Всё вне меток aidesign — тоже.

Какой файл — правило 6-handoff.md §2, первое совпадение: файл с блоком; AGENTS.md (или
CLAUDE.md, где только «@AGENTS.md»); один свой CLAUDE.md — блок в него, AGENTS.md не
заводится; ничего нет — AGENTS.md с блоком и CLAUDE.md из строки «@AGENTS.md».
Другие файлы правил агентов (GEMINI.md, .cursorrules, .cursor/rules/,
.github/copilot-instructions.md, .windsurfrules) получают одну строку-указатель, один раз
и только если уже есть. Ссылки, ведущие за пределы проекта, не трогаются.
"""

import datetime as dt
import os
from typing import List, Optional, Tuple

START, END = "<!-- aidesign:start -->", "<!-- aidesign:end -->"
NOW_START, NOW_END = "<!-- aidesign:now:start -->", "<!-- aidesign:now:end -->"
HEADING = "## Дизайн (AI Design)"
NOW_HEADING = "### Сейчас — пишет `ad.py` после каждого события, руками не правится"
POINTER_FILES = ("GEMINI.md", ".cursorrules", ".github/copilot-instructions.md", ".windsurfrules")
CURSOR_RULE = ".cursor/rules/aidesign.mdc"
POINTER_MARK = "подробности — блок `aidesign`"
FIGMA_MODE = {"free": "бесплатный путь — кадры 1280 и 390", "paid": "платный — файл разложен по разделам"}


def inside(root: str, path: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base.rstrip(os.sep) + os.sep)


def read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except OSError:
        return None


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def own_claude_md(root: str) -> bool:
    """Свой CLAUDE.md без AGENTS.md: блок aidesign пишется в него, второй файл памяти не заводится."""
    claude, agents = os.path.join(root, "CLAUDE.md"), os.path.join(root, "AGENTS.md")
    if os.path.lexists(agents) or not os.path.lexists(claude):
        return False
    text = read(claude)
    return text is None or text.strip() != "@AGENTS.md"


def _lines(text: str):
    """(начало строки, строка без перевода, вне огороженного кода ли) — по каждой строке."""
    pos, fence = 0, None
    for raw in text.splitlines(True):
        line = raw.rstrip("\r\n")
        mark = line.lstrip()[:3]
        if fence is None and mark in ("```", "~~~"):
            fence = mark
            yield pos, line, False
        elif fence is not None:
            if mark == fence:
                fence = None
            yield pos, line, False
        else:
            yield pos, line, True
        pos += len(raw)


def find_pair(text: str, start: str, end: str) -> Optional[Tuple[int, int, int]]:
    """Метки, каждая целиком на своей строке и вне блока кода: (начало строки start,
    начало строки end, конец строки end без перевода). Упомянутые в тексте метки — не блок."""
    a = None
    for pos, line, free in _lines(text):
        if not free or line.strip() not in (start, end):
            continue
        if a is None and line.strip() == start:
            a = pos
        elif a is not None and line.strip() == end:
            return a, pos, pos + len(line)
    return None


def find_block(text: str) -> Optional[Tuple[int, int, int]]:
    return find_pair(text or "", START, END)


def memory_file(root: str) -> Tuple[str, bool]:
    """(имя файла памяти, нужен ли рядом CLAUDE.md из одной строки)."""
    for name in ("AGENTS.md", "CLAUDE.md"):
        if find_block(read(os.path.join(root, name)) or ""):
            return name, False
    if own_claude_md(root):
        return "CLAUDE.md", False
    none = not any(os.path.lexists(os.path.join(root, n)) for n in ("AGENTS.md", "CLAUDE.md"))
    return "AGENTS.md", none


def _when(iso: Optional[str]) -> str:
    return (iso or "")[:16].replace("T", " ") or "—"


def _last(backups: list, word: str) -> Optional[str]:
    hit = [b for b in backups if str(b.get("reason") or "").lower().startswith(word)]
    return hit[-1]["id"] if hit else None


def now_lines(root: str, state: Optional[dict], event: str, work: str = ".aidesign-work") -> List[str]:
    """Факты для «Сейчас» — из state.js и диска, без советов."""
    s = state or {}
    stamp = s.get("updatedAt") or dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    out = ["- Обновлено: %s — %s." % (_when(stamp), event)]
    d = s.get("direction") or {}
    out.append("- Направление: «%s» — правила в `%s`, читай перед любой видимой правкой." % (d["name"], d.get("file") or "DESIGN.md")
               if d.get("name") else "- Направление: ещё не выбрано — `DESIGN.md` появится после выбора превью.")
    if os.path.isfile(os.path.join(root, "design-system", "tokens.css")):
        out.append("- Дизайн-система: `design-system/` — источник стиля `design-system/tokens.css`, витрина "
                   "`design-system/styleguide.html`, журнал `design-system/CHANGELOG.md`.")
    else:
        out.append("- Дизайн-система: ещё нет — `design-system/` появится на сборке.")
    backups = [b for b in s.get("backups") or [] if isinstance(b, dict) and b.get("id")]
    if backups:
        before, after = _last(backups, "до"), _last(backups, "после")
        target = before or backups[-1]["id"]
        out.append("- Копии проекта: «до» — %s, «после» — %s; все — `python3 %s/backup.py list --root .`. "
                   "Вернуть как было — только по слову человека: `python3 %s/backup.py restore --root . --id %s` "
                   "показывает план, с `--yes` откатывает (сначала копирует текущее, лишнее уносит в `<id>-лишнее/`)."
                   % ("`%s`" % before if before else "ещё нет", "`%s`" % after if after else "ещё нет", work, work, target))
    else:
        out.append("- Копии проекта: ещё нет.")
    f = s.get("figma") or {}
    out.append("- Figma: %s (%s); обновить — `/aidesign` и «обнови Figma»." % (f["url"], FIGMA_MODE.get(f.get("mode"), f.get("mode")))
               if f.get("url") else "- Figma: не подключена.")
    t = s.get("toolkit")
    if isinstance(t, dict):
        miss = ", ".join(t.get("missing") or []) or "ничего"
        out.append("- Оснащение (проверено %s): не хватает — %s." % (_when(t.get("checkedAt")), miss))
    if s.get("dir"):
        how = "сдан %s" % _when(s["finishedAt"]) if s.get("finishedAt") else "идёт"
        out.append("- Прогон: `%s/%s/` — %s; панель — `python3 %s/ad.py`." % (work, s["dir"], how, work))
    return out


def now_block(lines: List[str], nl: str = "\n") -> str:
    return nl.join([NOW_HEADING, NOW_START] + lines + [NOW_END])


def new_block(now: str, nl: str = "\n", work: str = ".aidesign-work") -> str:
    """Блок, когда его ещё нет: «Сейчас» и короткая памятка. Полный текст допишет агент на Передаче."""
    return nl.join([START, HEADING, "", now, "",
                    "- Правила дизайна — `DESIGN.md`, стиль — только из `design-system/`.",
                    "- Проверка: `python3 %s/check.py <файлы сайта>`." % work,
                    "- Копии и откат: `python3 %s/backup.py list --root .`." % work,
                    END]) + nl


def put_now(text: str, now: str, nl: str) -> str:
    """Заменить «Сейчас» внутри блока; нет его — вставить после заголовка блока. Чужое не трогается."""
    i, j, _ = find_block(text)
    inner = text[i:j]
    rows = list(_lines(inner))
    pair = find_pair(inner, NOW_START, NOW_END)
    if pair:
        a, _, b = pair
        prev = [p for p, line, free in rows if p < a and line.strip()]
        if prev and free_line(rows, prev[-1]) == NOW_HEADING:
            a = prev[-1]
        return text[:i] + inner[:a] + now + inner[b:] + text[j:]
    heading = [p for p, line, free in rows if free and line.strip() == HEADING]
    at = heading[0] if heading else 0                      # строка заголовка блока, иначе метки начала
    line = next(l for p, l, _ in rows if p == at)
    cut = at + len(line)
    cut += len(nl) if inner[cut:cut + len(nl)] == nl else (1 if inner[cut:cut + 1] == "\n" else 0)
    head = inner[:cut] if inner[:cut].endswith("\n") else inner[:cut] + nl
    return text[:i] + head + nl + now + nl + inner[cut:] + text[j:]


def free_line(rows, pos: int) -> Optional[str]:
    """Строка вне кода, начинающаяся в pos, без пробелов по краям; в коде — None."""
    for p, line, free in rows:
        if p == pos:
            return line.strip() if free else None
    return None


def update(root: str, state: Optional[dict], event: str, work: str = ".aidesign-work") -> List[str]:
    """Переписать «Сейчас» (или завести блок) и разложить строки-указатели. Возвращает заметки."""
    name, claude_too = memory_file(root)
    path = os.path.join(root, name)
    if os.path.lexists(path) and not inside(root, path):
        return ["! %s — ссылка за пределы проекта: блок aidesign не обновлён" % name]
    text = read(path)
    if os.path.lexists(path) and text is None:
        return ["! %s не читается — блок aidesign не обновлён" % name]
    text = text or ""
    nl = "\r\n" if "\r\n" in text else "\n"
    now = now_block(now_lines(root, state, event, work), nl)
    notes = []
    if find_block(text):
        new = put_now(text, now, nl)
        said = "правила проекта обновлены: %s → «Сейчас»" % name
    else:
        new = text + ("" if not text else ("" if text.endswith(nl) else nl) + nl) + new_block(now, nl, work)
        said = "блок aidesign заведён в %s (в конце файла, остальное не тронуто)" % name
    if new != text:
        write(path, new)
        notes.append(said)
    if claude_too:
        write(os.path.join(root, "CLAUDE.md"), "@AGENTS.md\n")
        notes.append("создан CLAUDE.md — одна строка @AGENTS.md")
    return notes + pointers(root, name)


def pointer_line(name: str) -> str:
    return "Дизайн: правила — `DESIGN.md`, стиль — `design-system/`, %s в `%s`." % (POINTER_MARK, name)


def pointers(root: str, name: str) -> List[str]:
    """Одна строка в конец уже существующих файлов правил других агентов, один раз."""
    notes, line = [], pointer_line(name)
    seen = {os.path.realpath(os.path.join(root, n)) for n in ("AGENTS.md", "CLAUDE.md")
            if os.path.lexists(os.path.join(root, n))}     # файл памяти — никогда не указатель
    for rel in POINTER_FILES:
        path = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(path) or not inside(root, path) or os.path.realpath(path) in seen:
            continue
        seen.add(os.path.realpath(path))
        text = read(path)
        if text is None or POINTER_MARK in text:
            continue
        nl = "\r\n" if "\r\n" in text else "\n"
        write(path, text + ("" if not text or text.endswith(("\n", "\r")) else nl) + line + nl)
        notes.append("строка-указатель дописана в %s" % rel)
    folder = os.path.join(root, ".cursor", "rules")
    rule = os.path.join(root, *CURSOR_RULE.split("/"))
    if os.path.isdir(folder) and inside(root, folder) and not os.path.lexists(rule):
        write(rule, "---\ndescription: Дизайн проекта (AI Design)\nalwaysApply: true\n---\n%s\n" % line)
        notes.append("создан %s со строкой-указателем" % CURSOR_RULE)
    return notes
