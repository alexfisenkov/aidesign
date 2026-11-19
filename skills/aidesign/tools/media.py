#!/usr/bin/env python3
"""Медиа для AI Design: какие генераторы подключены, как подключить, скачать и подготовить файлы.

    python3 media.py detect --tools a,b,c | --tools-file F [--json]   # агент передаёт свой список инструментов
    python3 media.py connect <сервис> --host claude|codex [--url U] [--json]   # только печатает команду
    python3 media.py skills [--roots …] [--json]                       # скиллы и инструкции про медиа
    python3 media.py fetch --url U --out assets/media/hero [--limit-mb 500] [--json]
    python3 media.py prep image|video --in F --out DIR [--json]
    python3 media.py record --slot hero --file assets/media/hero.webp --source own|<сервис>|code|placeholder
    python3 media.py list [--json]

Каталог генераторов — данные: knowledge/медиа/генераторы.json (рядом с этим файлом после init,
или в папке навыка). Ничего не генерирует, не тратит и не подключает само. Пути — от корня
проекта (--root, по умолчанию текущая папка); запись за корень и сквозь ссылки — отказ.
Коды: 0 — хорошо, 1 — отказ или нехватка (тип, размер, путь), 2 — ошибка ввода или нет ffmpeg.
"""

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = "генераторы.json"
MB = 1024 * 1024
ROLES = ("generate", "balance", "price", "wait", "download")
KIND_RU = {"image": "картинки", "video": "видео", "audio": "звук", "3d": "3D", "vector": "вектор", "svg": "SVG",
           "shader": "шейдеры"}
KIND_OF = {"png": "image", "jpeg": "image", "gif": "image", "webp": "image", "avif": "image", "svg": "svg",
           "mp4": "video", "mov": "video", "webm": "video", "glb": "3d", "mp3": "audio", "wav": "audio"}
EXT = {"jpeg": "jpg"}
SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv"}
FFMPEG_HINT = "ffmpeg не найден — поставить: python3 .aidesign-work/setup.py plan ffmpeg (затем install ffmpeg --yes)"


class InputError(Exception):
    """Ошибка ввода — код 2."""


class Refused(Exception):
    """Отказ: путь, ссылка, тип, размер, сеть — код 1."""


@dataclass
class Found:
    id: str
    title: str
    kinds: List[str]
    server: str
    tools: Dict[str, List[str]]
    known: bool = True
    unverified: bool = False
    auth: Optional[str] = None


# ── каталог и распознавание ─────────────────────────────────────────────────

def catalog_path(given: Optional[str] = None) -> str:
    places = [given] if given else []
    places += [os.path.join(HERE, CATALOG), os.path.join(HERE, "..", "knowledge", "медиа", CATALOG)]
    try:                                                  # копия в .aidesign-work/: папка навыка из state.js
        raw = open(os.path.join(HERE, "state.js"), encoding="utf-8").read()
        skill = json.loads(raw.split("=", 1)[1].strip().rstrip(";")).get("skillDir")
        if skill:
            places.append(os.path.join(skill, "knowledge", "медиа", CATALOG))
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    for p in places:
        if p and os.path.isfile(p):
            return p
    raise InputError("каталога %s нет — нужен --catalog или init --skill-dir" % CATALOG)


def load_catalog(path: Optional[str] = None) -> dict:
    with open(catalog_path(path), encoding="utf-8") as f:
        return json.load(f)


def split_name(name: str):
    """(сервер, инструмент): mcp__<сервер>__<инструмент>; встроенное — ("", имя)."""
    if name.startswith("mcp__"):
        server, _, tool = name[5:].partition("__")
        return server, tool
    return "", name


def _roles(names: List[str], exact: dict, generic: dict) -> Dict[str, List[str]]:
    out = {}
    for role in ROLES:
        hit = [n for n in names if split_name(n)[1] in (exact.get(role) or [])]
        if not hit and generic.get(role):
            hit = [n for n in names if re.search(generic[role], split_name(n)[1], re.I)]
        out[role] = hit
    return out


def _makers(names: List[str], gen: dict) -> List[str]:
    """Инструменты, которые что-то создают: общий шаблон каталога или роль generate."""
    role = (gen.get("roles") or {}).get("generate")
    return [n for n in names if any(re.search(p, n, re.I) for p in gen.get("match") or [])
            or (role and re.search(role, split_name(n)[1], re.I))]


def _kinds(names: List[str], gen: dict) -> List[str]:
    """Виды медиа по именам создающих инструментов: video, 3d, audio, svg… — не по имени сервера."""
    tools = " ".join(split_name(n)[1] for n in _makers(names, gen))
    return [k for k, p in (gen.get("kinds") or {}).items() if tools and re.search(p, tools, re.I)]


def _fingerprint(names: List[str], services: list) -> Optional[dict]:
    """Сервис по набору характерных инструментов: коннекторы claude.ai приходят с именем-UUID
    (mcp__cf833a6e-…__generate_video), по имени сервера их не узнать."""
    short = [split_name(n)[1] for n in names]
    best, score = None, 0
    for s in services:
        pats = s.get("fingerprint") or []
        need = s.get("fingerprint_need")
        if need and not any(re.search(need, t, re.I) for t in short):
            continue                              # набор похож, но генерирующего инструмента нет
        hit = sum(1 for p in pats if any(re.search(p, t, re.I) for t in short))
        if hit >= int(s.get("fingerprint_min") or 2) and hit > score:
            best, score = s, hit
    return best


def detect(tool_names: List[str], catalog: Optional[dict] = None) -> List[Found]:
    cat = catalog or load_catalog()
    gen = cat.get("generic") or {}
    names = list(dict.fromkeys(n.strip() for n in tool_names if n and n.strip()))
    groups, rest = {}, {}
    by_server = {}
    for n in names:
        server = split_name(n)[0]
        if server:
            by_server.setdefault(server, []).append(n)
            continue
        svc = next((s for s in cat["services"] if any(re.search(p, n, re.I) for p in s["match"])), None)
        if svc:                                   # встроенное (image_gen) — по своему имени
            groups.setdefault((svc["id"], ""), (svc, []))[1].append(n)
    for server, ns in by_server.items():          # сервер целиком: по имени, иначе по отпечатку
        svc = next((s for s in cat["services"] if any(re.search(p, n, re.I) for p in s["match"] for n in ns)), None)
        svc = svc or _fingerprint(ns, cat["services"])
        if svc:
            groups[(svc["id"], server)] = (svc, ns)
        else:
            rest[server] = ns
    found, seen = [], {}
    for (_, server), (s, ns) in groups.items():
        by_tool = s.get("kinds_by_tools")
        kinds = ([k for k, p in by_tool.items() if any(re.search(p, split_name(n)[1], re.I) for n in ns)] if by_tool
                 else list(dict.fromkeys(list(s["kinds"]) + _kinds(ns, gen))))
        f = Found(s["id"], s["title"], kinds, server, _roles(ns, s["tools"], gen.get("roles") or {}),
                  True, bool(s.get("unverified")), s.get("auth"))
        size = len(ns)
        if s["id"] in seen:                       # один сервис под двумя именами — строка с большим набором
            i, was = seen[s["id"]]
            if size > was:
                found[i], seen[s["id"]] = f, (i, size)
            continue
        seen[s["id"]] = (len(found), size)
        found.append(f)
    for server, ns in rest.items():
        kinds = _kinds(ns, gen)
        if kinds:
            found.append(Found(server, server, kinds, server, _roles(ns, {}, gen.get("roles") or {}), False, True))
    return found


def connect(sid: str, host: str, catalog: Optional[dict] = None, url: Optional[str] = None):
    """(команды, заметки). Ничего не выполняет: команду запускают после «да» человека, вход — он сам."""
    if host not in ("claude", "codex"):
        raise InputError("--host claude | codex")
    cat = catalog or load_catalog()
    svc = next((s for s in cat["services"] if s["id"] == sid), None)
    notes = []
    if svc and svc.get("builtin"):
        return [], [svc.get("notes") or "встроено — подключать не нужно"]
    cmds = list((svc or {}).get("connect", {}).get(host) or [])
    if not cmds:
        name = re.sub(r"[^a-z0-9-]+", "-", sid.lower()).strip("-") or "generator"
        cmds = [c.replace("<имя>", name).replace("<URL>", url or "<URL>")
                for c in (cat.get("generic") or {}).get("connect", {}).get(host, [])]
        notes.append("официальной команды в каталоге нет — общий шаблон" + ("" if url else ": адрес сервера MCP (<URL>) возьмите у сервиса"))
    auth = (svc or {}).get("auth", "oauth")
    if auth == "key":
        notes.append("ключ %s возьмите в кабинете сервиса и подставьте в команду сами; в чат его не присылайте"
                     % svc.get("key_env", ""))
    elif host == "claude":
        notes.append("вход: в Claude Code наберите /mcp, выберите сервер и войдите в аккаунт в браузере — входите вы сами")
    else:
        notes.append("codex mcp login откроет браузер — входите в аккаунт вы сами")
    notes.append("команда ничего не делает без вашего «да»; после подключения начните новую сессию")
    if svc and svc.get("unverified"):
        notes.append("часть сведений о сервисе не сверена с официальной страницей: %s"
                     % ", ".join(svc.get("unverified_fields") or ["—"]))
    return cmds, notes


# ── скиллы про медиа ────────────────────────────────────────────────────────

def default_roots() -> List[str]:
    home = os.path.expanduser("~")
    return [os.path.join(home, ".claude", "skills"), os.path.join(home, ".claude", "plugins"),
            os.path.join(home, ".codex", "skills"), os.path.join(home, ".agents", "skills"),
            os.path.join(".claude", "skills"), os.path.join(".agents", "skills")]


def front(text: str) -> dict:
    """name и description из шапки SKILL.md (одна строка или блок > / |)."""
    if not text.startswith("---"):
        return {}
    out, key = {}, None
    for line in text.split("\n---", 1)[0].splitlines()[1:]:
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("\"'")
        elif key and line.startswith((" ", "\t")):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


_W = r"(?:[\w/'’-]+[\s,]+){0,5}?"                  # после «генерировать»: до пяти слов, через запятые
_N = r"(?:[\w/'’-]+\s+){0,2}?"                      # у «промптов»: до двух слов, без знаков препинания
# Признаки скилла про медиа: (вес, причина, шаблон). Слово «промпт» или «видео» само по себе — не признак:
# скилл должен быть про генерацию медиа или промпты к генераторам картинок, видео, звука, 3D, шейдеров.
SKILL_SIGNS = [
    (3, "генераторы: {}", re.compile(
        r"\b(midjourney|flux|kling|seedance|veo ?\d?|sora|higgsfield|magnific|freepik|runway|comfyui|nano.?banana|"
        r"gpt.?image|dall.?e|imagen|stable.?diffusion|sdxl|suno|elevenlabs|luma|pika|recraft|meshy|krea|leonardo|"
        r"ideogram|syntx|hailuo|hunyuan|minimax)\b", re.I)),
    (3, "генерация медиа", re.compile(
        r"\bgenerat\w*\s+" + _W + r"(images?|videos?|photos?|pictures?|audio|music|songs?|speech|voices?|sound|3d|"
        r"clips?|visuals?|illustrations?|textures?|sprites?)\b|"
        r"генер\w*\s+" + _W + r"(изображ|картин|видео|фото|ролик|звук|музык|песн|озвуч|3d|иллюстрац)|"
        r"(изображ|картин|видео|фото|ролик)\w*\s+" + _N + r"генер|"
        r"\b(text|image|img|photo)[ -]?(to|2)[ -]?(image|img|video|vid|speech|3d|music)\b|"
        r"\b(images?|videos?)\b[\w\s,]{0,30}\bcreative\b|(картин|видео)\w*[\w\s,]{0,30}креатив", re.I)),
    (3, "промпты к генераторам", re.compile(
        r"\b(image|video|motion|photo|visual|art)\s+prompts?\b|\bprompts?\s+(for|to)\s+" + _N +
        r"(images?|videos?|photos?|ai art|generat\w*)\b|"
        r"промпт\w*\s+" + _N + r"(картин|изображ|видео|фото|нейросет|генерац|генератор)|"
        r"(видео|фото|картин)\w*-промпт", re.I)),
    (3, "шейдеры и 3D", re.compile(r"\bshaders?\b|шейдер|\b3d[ -](models?|assets?|scenes?)\b|3d-модел", re.I)),
]


def skill_score(text: str, body: str = ""):
    """(баллы, причина) — сколько признаков и каких в имени и описании; 0 — скилл не про медиа.
    Текст скилла добавляет баллы, только если в нём три и больше разных генераторов."""
    score, why = 0, []
    for weight, label, rx in SKILL_SIGNS:
        hits = list(dict.fromkeys(m.group(0).strip().lower() for m in rx.finditer(text)))
        if hits:
            score += weight + len(hits) - 1
            why.append(label.format(", ".join(hits[:4])) if "{}" in label else label)
    named = list(dict.fromkeys(m.group(0).strip().lower() for m in SKILL_SIGNS[0][2].finditer(body)))
    if len(named) >= 3:
        score += 3
        why.append("в тексте скилла: " + ", ".join(named[:4]))
    return score, "; ".join(why)


def skills(roots: Optional[List[str]] = None, depth: int = 7) -> List[dict]:
    """Скиллы про генерацию медиа и промпты к генераторам — по одной строке на имя (копии в разных
    папках — в paths), по убыванию соответствия, с короткой причиной."""
    found, seen = {}, set()
    for root in roots or default_roots():
        root = os.path.abspath(root)
        for base, dirs, names in os.walk(root, followlinks=True):
            real = os.path.realpath(base)
            if real in seen or base[len(root):].count(os.sep) >= depth:
                dirs[:] = []
                continue
            seen.add(real)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            if "SKILL.md" not in names:
                continue
            try:
                text = open(os.path.join(base, "SKILL.md"), encoding="utf-8").read(65536)
                meta = front(text)
            except (OSError, UnicodeDecodeError):
                continue
            name, about = meta.get("name") or os.path.basename(base), meta.get("description") or ""
            if name == "aidesign":
                continue
            score, why = skill_score(name.replace("-", " ") + ". " + about, text.split("\n---", 1)[-1])
            if not score:
                continue
            path = os.path.join(base, "SKILL.md")
            have = found.get(name.lower())
            if have:
                if os.path.realpath(path) not in {os.path.realpath(p) for p in have["paths"]}:
                    have["paths"].append(path)
                continue
            found[name.lower()] = {"name": name, "about": about[:240], "path": path, "paths": [path],
                                   "score": score, "why": why}
    return sorted(found.values(), key=lambda s: (-s["score"], s["name"].lower()))


# ── пути внутри проекта ─────────────────────────────────────────────────────

def target(root: str, rel: str) -> str:
    """Абсолютный путь внутри корня, где ни одна существующая часть — не ссылка."""
    real = os.path.realpath(root)
    path = os.path.normpath(rel if os.path.isabs(rel) else os.path.join(real, rel))
    for base in (real, os.path.abspath(root)):
        if path == base or path.startswith(base.rstrip(os.sep) + os.sep):
            cur = base
            for part in os.path.relpath(path, base).split(os.sep):
                cur = os.path.join(cur, part)
                if os.path.islink(cur):
                    raise Refused("%s — ссылка: запись сквозь неё ушла бы за пределы проекта" % os.path.relpath(cur, base))
            return os.path.join(real, os.path.relpath(path, base))
    raise Refused("%s — вне папки проекта: пишу только внутрь неё" % rel)


def make_dir(root: str, rel: str) -> str:
    path = target(root, rel)
    os.makedirs(path, exist_ok=True)
    if not os.path.realpath(path).startswith(os.path.realpath(root).rstrip(os.sep) + os.sep):
        raise Refused("папка %s оказалась вне проекта" % rel)
    return path


def rel_to(root: str, path: str) -> str:
    return os.path.relpath(path, os.path.realpath(root)).replace(os.sep, "/")


# ── скачивание ──────────────────────────────────────────────────────────────

def sniff(b: bytes) -> Optional[str]:
    """Формат по первым байтам; None — не медиа (страница ошибки, архив, неизвестное)."""
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if b[:4] == b"RIFF" and b[8:12] in (b"WEBP", b"WAVE"):
        return "webp" if b[8:12] == b"WEBP" else "wav"
    if b[4:8] == b"ftyp":
        brand = b[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"heis"):
            return None
        return "mov" if brand == b"qt  " else "mp4"
    if b[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if b[:4] == b"glTF":
        return "glb"
    if (b[:3] == b"ID3" and len(b) >= 10 and b[3] in (2, 3, 4)) or frame_len(b[:4]):     # подробно — mp3_ok
        return "mp3"
    text = b.lstrip(b"\xef\xbb\xbf \t\r\n")[:4096].decode("utf-8", "ignore").lower()
    if re.match(r"(<\?xml[^>]*\?>\s*)?(<!--.*?-->\s*)*(<!doctype[^>\[]*(\[.*?\])?\s*>\s*)?<([\w.-]+:)?svg[\s>/]", text, re.S):
        return "svg"
    return None


SAME_EXT = {"jpeg": ("jpg", "jpeg"), "mp4": ("mp4", "m4v"), "mp3": ("mp3",), "glb": ("glb",)}


def place(tmp: str, dest: str) -> str:
    """Готовый файл — на свободное имя: занято (файл человека, ссылка) — «имя-2», «имя-3»…
    Жёсткая ссылка не затирает существующее; без них (FAT, exFAT) — проверка и переименование."""
    base, ext = os.path.splitext(dest)
    n, cand = 1, dest
    while True:
        try:
            os.link(tmp, cand)
        except FileExistsError:
            n += 1
            cand = "%s-%d%s" % (base, n, ext)
            continue
        except OSError:
            if os.path.lexists(cand):
                n += 1
                cand = "%s-%d%s" % (base, n, ext)
                continue
            os.replace(tmp, cand)
            return cand
        os.remove(tmp)
        return cand


def real_ext(root: str, dest: str, fmt: str):
    """(путь с расширением настоящего формата, заменено ли): PNG под именем clip.mp4 станет clip.png."""
    stem, ext = os.path.splitext(dest)
    if ext[1:].lower() in SAME_EXT.get(fmt, (fmt,)):
        return dest, False
    return target(root, rel_to(root, stem + "." + EXT.get(fmt, fmt))), bool(ext)


# ── проверка содержимого: MP3 по кадрам, SVG разбором ───────────────────────

_BR = {(3, 3): (32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448),     # MPEG-1, слой I
       (3, 2): (32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384),       # MPEG-1, слой II
       (3, 1): (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),        # MPEG-1, слой III
       (2, 3): (32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256),       # MPEG-2/2.5, слой I
       (2, 2): (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)}            # MPEG-2/2.5, слои II и III
_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def frame_len(h: bytes) -> Optional[int]:
    """Длина кадра MPEG-аудио по его заголовку; None — это не заголовок кадра."""
    if len(h) < 4 or h[0] != 0xFF or h[1] & 0xE0 != 0xE0:
        return None
    ver, layer, bri, sri, pad = (h[1] >> 3) & 3, (h[1] >> 1) & 3, h[2] >> 4, (h[2] >> 2) & 3, (h[2] >> 1) & 1
    if ver == 1 or layer == 0 or bri in (0, 15) or sri == 3:
        return None
    br = _BR[(3, layer) if ver == 3 else (2, 3 if layer == 3 else 2)][bri - 1] * 1000
    sr = _SR[ver][sri]
    if layer == 3:
        return (12 * br // sr + pad) * 4
    return (144 if ver == 3 or layer == 2 else 72) * br // sr + pad


def mp3_ok(path: str) -> bool:
    """ID3 — полный заголовок (версия 2–4, синхробезопасный размер), за тегом — кадры; без ID3 —
    два подряд корректных кадра на расстоянии, которое задаёт первый (битрейт, частота, паддинг)."""
    with open(path, "rb") as f:
        h = f.read(10)
        off = 0
        if h[:3] == b"ID3":
            if len(h) < 10 or h[3] not in (2, 3, 4) or h[4] == 0xFF or any(b >= 0x80 for b in h[6:10]):
                return False
            size = (h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9]
            off = 10 + size + (10 if h[3] == 4 and h[5] & 0x10 else 0)
        f.seek(off)
        first = f.read(4)
        n = frame_len(first)
        if not n:
            return False
        f.seek(off + n)
        return frame_len(f.read(4)) is not None


SVG_NS, XLINK_NS = "http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink"
# Неживые пространства имён редакторов: браузер их не исполняет и не грузит.
INERT_NS = {"http://www.inkscape.org/namespaces/inkscape", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "http://purl.org/dc/elements/1.1/",
            "http://creativecommons.org/ns#", "http://ns.adobe.com/AdobeIllustrator/10.0/"}
SAFE_SVG = set("""svg g defs title desc metadata symbol use path rect circle ellipse line polyline polygon text tspan
textPath linearGradient radialGradient stop pattern clipPath mask marker filter image style switch view
animate animateTransform animateMotion mpath feBlend feColorMatrix feComponentTransfer feComposite
feConvolveMatrix feDiffuseLighting feDisplacementMap feDistantLight feDropShadow feFlood feFuncA feFuncB feFuncG
feFuncR feGaussianBlur feImage feMerge feMergeNode feMorphology feOffset fePointLight feSpecularLighting
feSpotLight feTile feTurbulence""".split())
SAFE_HREF = re.compile(r"^(#[\w.:-]*|data:image/(png|jpeg|gif|webp|avif)[;,])", re.I)
BAD_CSS = re.compile(r"@import|javascript:|expression\(|-moz-binding|behavior\s*:|url\(\s*['\"]?(?!#|data:image/(png|jpeg|gif|webp|avif)[;,])",
                     re.I)


def _plain(v: str) -> str:
    return re.sub(r"[\s\x00-\x1f]+", "", v or "").lower()


def svg_problem(data: bytes) -> Optional[str]:
    """Почему SVG небезопасен, или None. Разбор, а не поиск слов: сущности раскрывает парсер,
    DOCTYPE и ENTITY не принимаются вовсе (внешних сущностей нет), инструкции, кроме <?xml?>, — тоже."""
    import xml.etree.ElementTree as ET
    text = data.decode("utf-8", "replace")
    if re.search(r"<!doctype|<!entity", text, re.I):
        return "внутри DOCTYPE или ENTITY"
    rest = text.lstrip("﻿ \t\r\n")
    if rest.startswith("<?xml"):
        rest = rest[rest.find("?>") + 2:]
    if "<?" in rest:
        return "внутри инструкция обработки"
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        return "не разбирается как XML (%s)" % e
    if root.tag not in ("{%s}svg" % SVG_NS, "svg"):
        return "корень — не svg"
    for el in root.iter():
        ns, _, local = el.tag[1:].partition("}") if el.tag.startswith("{") else ("", "", el.tag)
        if ns in INERT_NS:
            continue
        if ns not in (SVG_NS, "") or local not in SAFE_SVG:
            return "элемент %s" % local
        for key, val in el.attrib.items():
            name = key.rpartition("}")[2]
            if name.lower().startswith("on"):
                return "обработчик %s=" % name
            if name == "href" and not SAFE_HREF.match((val or "").strip()):
                return "ссылка %s на «%s»" % (name, (val or "")[:40])
            if "javascript:" in _plain(val) or (name == "style" and BAD_CSS.search(val or "")):
                return "атрибут %s" % name
            if name == "attributeName" and (val.lower().startswith("on") or val.endswith("href")):
                return "анимация %s" % val
        if local == "style" and BAD_CSS.search("".join(el.itertext())):
            return "стиль с внешней загрузкой"
    return None


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme not in ("http", "https"):
            raise Refused("сервис перенаправил не на http(s): %s" % urllib.parse.urlparse(newurl).scheme)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, out: str, root: str = ".", limit_mb: float = 500) -> dict:
    """Скачать в проект. Существующий файл не затирается — новое имя «-2»; расширение — по формату."""
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise InputError("скачиваю только http:// и https://, а не «%s»" % url[:60])
    dest = target(root, out)
    if os.path.isdir(dest):
        raise InputError("--out — путь к файлу, а %s — папка" % out)
    folder = make_dir(root, rel_to(root, os.path.dirname(dest)))
    limit = int(limit_mb * MB)
    opener = urllib.request.build_opener(_Redirect)
    req = urllib.request.Request(url, headers={"User-Agent": "aidesign-media/1"})
    try:
        r = opener.open(req, timeout=60)
    except urllib.error.HTTPError as e:
        raise Refused("сервер ответил %d — ссылка устарела или закрыта; возьмите свежую у сервиса" % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise Refused("не скачалось: %s" % getattr(e, "reason", e))
    fd, tmp = tempfile.mkstemp(prefix=".media-", suffix=".part", dir=folder)
    try:
        with r, os.fdopen(fd, "wb") as f:
            size = r.headers.get("Content-Length")
            if size and size.isdigit() and int(size) > limit:
                raise Refused("файл %.1f МБ больше лимита %s МБ" % (int(size) / MB, limit_mb))
            total, first = 0, b""
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise Refused("файл больше лимита %s МБ — скачивание остановлено" % limit_mb)
                if len(first) < 4096:
                    first += chunk[:4096 - len(first)]
                f.write(chunk)
        fmt = sniff(first)
        if not fmt:
            raise Refused("это не картинка, видео, звук или 3D (первые байты не похожи) — ссылка, скорее всего, "
                          "ведёт на страницу ошибки")
        if fmt == "svg":
            with open(tmp, "rb") as f:
                why = svg_problem(f.read())
            if why:
                raise Refused("небезопасный SVG (%s) — не сохранён; попросите у сервиса чистый SVG или растровую "
                              "картинку" % why)
        if fmt == "mp3" and not mp3_ok(tmp):
            raise Refused("это не MP3: после заголовка нет корректных кадров звука — скорее всего, страница ошибки")
        dest, renamed = real_ext(root, dest, fmt)
        final = place(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    notes = (["расширение заменено на настоящее: .%s" % EXT.get(fmt, fmt)] if renamed else []) + \
        (["%s уже был — новый файл рядом, старый не тронут" % rel_to(root, dest)] if final != dest else [])
    return {"file": rel_to(root, final), "format": fmt, "kind": KIND_OF[fmt], "bytes": total, "url": url, "notes": notes}


# ── подготовка через ffmpeg ─────────────────────────────────────────────────

def which(name: str) -> Optional[str]:
    path = os.environ.get("AIDESIGN_MEDIA_PATH")                 # шов тестов: подмена PATH
    return shutil.which(name, path=path) if path is not None else shutil.which(name)


def ffmpeg() -> str:
    p = which("ffmpeg")
    if not p:
        raise InputError(FFMPEG_HINT)
    return p


def _tmp(folder: str, ext: str) -> str:
    fd, path = tempfile.mkstemp(prefix=".part-", suffix="." + ext, dir=folder)
    os.close(fd)
    return path


def _ffrun(ff: str, args: List[str], dst: str) -> None:
    """ffmpeg пишет только в свой временный файл (-y — по нему же)."""
    r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-nostdin"] + args + [dst],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    if r.returncode or not os.path.getsize(dst):
        raise Refused("ffmpeg не справился с %s: %s" % (os.path.basename(dst), (r.stderr or "").strip()[-300:]))


def _ff(ff: str, args: List[str], out: str) -> str:
    """Во временный файл, затем на свободное имя рядом с out. Возвращает итоговый путь."""
    tmp = _tmp(os.path.dirname(out), os.path.splitext(out)[1][1:])
    try:
        _ffrun(ff, args, tmp)
        return place(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def encoders(ff: str) -> set:
    r = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, errors="replace")
    return set(re.findall(r"^\s*[VAS][\w.]{5}\s+(\S+)", r.stdout, re.M))


def size_of(ff: str, src: str):
    r = subprocess.run([ff, "-hide_banner", "-i", src], capture_output=True, text=True, errors="replace")
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    if not m:
        raise Refused("ffmpeg не видит в %s картинку или видео" % os.path.basename(src))
    return int(m.group(1)), int(m.group(2))


def _webp(ff: str, enc: set, src: str, vf: str, out: str, notes: List[str]) -> Optional[str]:
    if "libwebp" in enc:
        return _ff(ff, ["-i", src, "-vf", vf, "-frames:v", "1", "-c:v", "libwebp", "-quality", "80"], out)
    cw = which("cwebp")
    if not cw:
        notes.append("WebP не сделан: в ffmpeg нет libwebp и нет cwebp — поставить: "
                     "python3 .aidesign-work/setup.py install webp --yes")
        return None
    folder = os.path.dirname(out)
    png, webp = _tmp(folder, "png"), _tmp(folder, "webp")
    try:
        _ffrun(ff, ["-i", src, "-vf", vf, "-frames:v", "1", "-update", "1"], png)
        r = subprocess.run([cw, "-quiet", "-q", "80", png, "-o", webp], capture_output=True, text=True)
        if r.returncode:
            raise Refused("cwebp не справился: %s" % r.stderr.strip()[-200:])
        return place(webp, out)
    finally:
        for p in (png, webp):
            if os.path.exists(p):
                os.remove(p)


def _avif(ff: str, enc: set, src: str, vf: str, out: str, notes: List[str]) -> Optional[str]:
    codec = next((c for c in ("libaom-av1", "libsvtav1", "librav1e") if c in enc), None)
    if not codec:
        notes.append("AVIF не сделан: в ffmpeg нет кодировщика AV1")
        return None
    extra = ["-still-picture", "1", "-crf", "30"] if codec == "libaom-av1" else ["-crf", "32"] if codec == "libsvtav1" else []
    return _ff(ff, ["-i", src, "-vf", vf, "-frames:v", "1", "-c:v", codec, "-pix_fmt", "yuv420p"] + extra + ["-f", "avif"], out)


def _source(root: str, src: str) -> str:
    path = src if os.path.isabs(src) else os.path.join(root, src)
    if not os.path.isfile(path):
        raise InputError("файла %s нет" % src)
    return path


def _variant(root: str, path: str, **kw) -> dict:
    return dict({"file": rel_to(root, path)}, **kw, bytes=os.path.getsize(path))


def prep_image(src: str, out_dir: str, widths=(640, 1280, 1920), formats=("webp", "avif"), root: str = ".") -> dict:
    """Файлы под сайт; уже лежащие с тем же именем не затираются — новые получают «-2», «-3»."""
    ff, path = ffmpeg(), _source(root, src)
    folder, notes, variants = make_dir(root, out_dir), [], []
    enc = encoders(ff)
    w0, _ = size_of(ff, path)
    sizes = sorted({w for w in widths if w <= w0} | ({w0} if max(widths) > w0 else set()))
    stem = os.path.splitext(os.path.basename(path))[0]
    for w in sizes:
        w -= w % 2
        for fmt in formats:
            out = target(root, rel_to(root, os.path.join(folder, "%s-%d.%s" % (stem, w, fmt))))
            vf = "scale=%d:-2" % w
            made = (_webp if fmt == "webp" else _avif)(ff, enc, path, vf, out, notes) if fmt in ("webp", "avif") \
                else _ff(ff, ["-i", path, "-vf", vf, "-frames:v", "1", "-update", "1", "-q:v", "3"], out)
            if made:
                variants.append(_variant(root, made, format=fmt, width=w))
    return {"src": rel_to(root, path), "kind": "image", "variants": variants, "notes": sorted(set(notes))}


def prep_video(src: str, out_dir: str, audio: bool = False, max_width: int = 1920, root: str = ".") -> dict:
    """MP4 H.264 (+faststart), WebM VP9, постер JPG и WebP; занятые имена — «-2», исходник не затирается."""
    ff, path = ffmpeg(), _source(root, src)
    folder, notes, variants = make_dir(root, out_dir), [], []
    enc = encoders(ff)
    stem = os.path.splitext(os.path.basename(path))[0]
    vf = "scale='min(%d,iw)':-2" % max_width
    out_for = lambda name: target(root, rel_to(root, os.path.join(folder, name)))
    sound = lambda codec: ["-c:a", codec] if audio else ["-an"]
    plans = [("mp4", "libx264", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium",
                                 "-movflags", "+faststart"] + sound("aac")),
             ("webm", "libvpx-vp9", ["-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", "-row-mt", "1"] + sound("libopus"))]
    for ext, codec, args in plans:
        if codec not in enc:
            notes.append("%s не сделан: в ffmpeg нет %s" % (ext.upper(), codec))
            continue
        variants.append(_variant(root, _ff(ff, ["-i", path, "-vf", vf] + args, out_for("%s.%s" % (stem, ext))), format=ext))
    poster = _ff(ff, ["-i", path, "-vf", vf, "-frames:v", "1", "-update", "1", "-q:v", "3"], out_for("%s-poster.jpg" % stem))
    variants.append(_variant(root, poster, format="jpg", role="poster"))
    webp = _webp(ff, enc, poster, "scale=iw:-2", out_for("%s-poster.webp" % stem), notes)
    if webp:
        variants.append(_variant(root, webp, format="webp", role="poster"))
    if not any(v["format"] in ("mp4", "webm") for v in variants):
        raise Refused("видео не подготовлено: %s" % "; ".join(notes))
    return {"src": rel_to(root, path), "kind": "video", "variants": variants, "notes": notes}


# ── опись assets/media.json ─────────────────────────────────────────────────

def _inventory(root: str) -> str:
    return target(root, os.path.join("assets", "media.json"))


def list_items(root: str = ".") -> dict:
    try:
        with open(_inventory(root), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"items": []}
    except ValueError:
        raise Refused("assets/media.json не разбирается — поправьте его или уберите в сторону")
    return data if isinstance(data.get("items"), list) else {"items": []}


BASE_SOURCES = ("own", "code", "placeholder")


def known_sources(catalog: Optional[dict] = None) -> set:
    """own, code, placeholder, id сервисов каталога и подключённые в прогоне (state.media.connected —
    там и неизвестные каталогу генераторы, которые нашёл detect)."""
    out = set(BASE_SOURCES)
    try:
        out |= {s["id"] for s in (catalog or load_catalog()).get("services") or [] if isinstance(s, dict)}
    except (InputError, OSError, ValueError, KeyError):
        pass
    try:
        raw = open(os.path.join(HERE, "state.js"), encoding="utf-8").read()
        media = json.loads(raw.split("=", 1)[1].strip().rstrip(";")).get("media") or {}
        out |= {c.get("id") for c in media.get("connected") or [] if isinstance(c, dict) and c.get("id")}
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    return out


def record(root: str, slot: str, file: str, source: str, kind: Optional[str] = None, prompt: str = "",
           model: str = "", alt: str = "", variants: Optional[list] = None, sources: Optional[set] = None) -> dict:
    """Строка описи. Файл должен быть на месте, источник — из известных: опись — не место для догадок."""
    if not slot or not SOURCE_RE.match(source or ""):
        raise InputError("--slot и --source own | code | placeholder | <id сервиса> (латиницей)")
    allowed = sources if sources is not None else known_sources()
    if source not in allowed:
        raise Refused("источник «%s» неизвестен: own, code, placeholder или id сервиса из каталога и подключённых "
                      "(ad.py media connected --ids …)" % source)
    if file and not os.path.isfile(target(root, file)):
        raise Refused("файла %s нет в проекте — сначала положите файл (media.py fetch или prep), потом опись" % file)
    if file and not kind:
        path = target(root, file)
        fmt = None
        if os.path.isfile(path):
            with open(path, "rb") as f:
                fmt = sniff(f.read(4096))
        fmt = fmt or {"jpg": "jpeg"}.get(os.path.splitext(file)[1][1:].lower(), os.path.splitext(file)[1][1:].lower())
        kind = KIND_OF.get(fmt)
    item = {"slot": slot, "file": file or None, "kind": kind, "source": source, "prompt": prompt or None,
            "model": model or None, "at": dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "alt": alt or None, "variants": variants or []}
    data = list_items(root)
    data["items"] = [i for i in data["items"] if i.get("slot") != slot] + [item]
    path = _inventory(root)
    make_dir(root, "assets")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return item


def rules_after_record(root: str, slot: str) -> List[str]:
    """«Сейчас» блока aidesign переписывает только ad.py: зовём его событием `media recorded`.
    Работает из копии в .aidesign-work/ (рядом ad.py и state.js) и только для проекта этого прогона."""
    ad = os.path.join(HERE, "ad.py")
    if not (os.path.isfile(ad) and os.path.isfile(os.path.join(HERE, "state.js"))):
        return []
    if os.path.realpath(os.path.dirname(HERE)) != os.path.realpath(root):
        return ["· «Сейчас» в правилах проекта не обновлено: опись лежит не в проекте этого прогона"]
    try:
        r = subprocess.run([sys.executable, ad, "media", "recorded", "--slot=" + slot, "--no-serve"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return ["! «Сейчас» в правилах проекта не обновлено: %s" % e]
    if r.returncode:
        return ["! «Сейчас» в правилах проекта не обновлено: %s" % (r.stdout + r.stderr).strip()[-200:]]
    said = [line.strip() for line in r.stdout.splitlines() if line.startswith("  ")]
    return [n if n.startswith(("·", "!")) else "· " + n for n in said if "правил" in n or "aidesign" in n]


# ── командная строка ────────────────────────────────────────────────────────

def _say(data, as_json: bool, text: str) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2) if as_json else text)


def _detect_text(found: List[Found]) -> str:
    if not found:
        return ("Генераторов среди инструментов не видно. Подключить: media.py connect <сервис> --host claude|codex "
                "(сервисы — knowledge/медиа/генераторы.json); без генератора — свои файлы, код или плашки.")
    rows = ["Подключено | умеет | баланс | цена | ожидание"]
    for f in found:
        have = lambda r: "есть" if f.tools.get(r) else "—"
        rows.append("%s%s | %s | %s | %s | %s" % (f.title, "" if f.known else " (неизвестный, по шаблону)",
                    ", ".join(KIND_RU.get(k, k) for k in f.kinds) or "?", have("balance"), have("price"), have("wait")))
    return "\n".join(rows)


def run(a) -> int:
    root = os.path.abspath(a.root)
    if a.cmd == "detect":
        names = re.split(r"[\s,]+", a.tools or "")
        if a.tools_file:
            text = open(a.tools_file, encoding="utf-8").read()
            names += json.loads(text) if text.lstrip().startswith("[") else re.split(r"[\s,]+", text)
        found = detect(names, load_catalog(a.catalog))
        _say([asdict(f) for f in found], a.json, _detect_text(found))
    elif a.cmd == "connect":
        cmds, notes = connect(a.id, a.host, load_catalog(a.catalog), a.url)
        _say({"id": a.id, "host": a.host, "commands": cmds, "notes": notes}, a.json,
             "\n".join(cmds + ["· " + n for n in notes]))
    elif a.cmd == "skills":
        found = skills(a.roots)
        _say(found, a.json, "\n".join("%s — %s\n  %s\n  %s%s" % (s["name"], s["why"], s["about"][:120], s["path"],
                                                                  " (ещё копий: %d)" % (len(s["paths"]) - 1)
                                                                  if len(s["paths"]) > 1 else "") for s in found)
             or "Скиллов про генерацию медиа и промпты к генераторам не нашлось — работаю по knowledge/медиа/.")
    elif a.cmd == "fetch":
        r = fetch(a.url, a.out, root, a.limit_mb)
        _say(r, a.json, "Скачано: %s (%s, %.1f МБ). Дальше — посмотреть глазами и media.py prep." % (
            r["file"], r["format"], r["bytes"] / MB) + "".join("\n· " + n for n in r["notes"]))
    elif a.cmd == "prep":
        r = (prep_image if a.what == "image" else prep_video)(a.src, a.out, root=root)
        _say(r, a.json, "\n".join(["Готово для сайта:"] + ["- %s" % v["file"] for v in r["variants"]]
                                  + ["! " + n for n in r["notes"]]))
        return 0 if r["variants"] else 1
    elif a.cmd == "record":
        cat = None
        try:
            cat = load_catalog(a.catalog)
        except (InputError, OSError, ValueError):
            pass
        item = record(root, a.slot, a.file, a.source, a.kind, a.prompt, a.model, a.alt, sources=known_sources(cat))
        notes = rules_after_record(root, item["slot"])
        _say(item, a.json, "В описи assets/media.json: %s — %s (%s)." % (item["slot"], item["file"] or "без файла",
                                                                         item["source"]) + "".join("\n" + n for n in notes))
    elif a.cmd == "list":
        data = list_items(root)
        _say(data, a.json, "\n".join("%s · %s · %s · %s" % (i.get("slot"), i.get("file") or "—", i.get("source"),
                                                             i.get("alt") or "без alt") for i in data["items"]) or "Опись пуста.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Медиа для AI Design")
    sub = p.add_subparsers(dest="cmd")
    for name in ("detect", "connect", "skills", "fetch", "prep", "record", "list"):
        x = sub.add_parser(name)
        x.add_argument("--json", action="store_true")
        x.add_argument("--root", default=".")
        x.add_argument("--catalog")
    s = sub.choices
    s["detect"].add_argument("--tools")
    s["detect"].add_argument("--tools-file")
    s["connect"].add_argument("id")
    s["connect"].add_argument("--host", required=True)
    s["connect"].add_argument("--url")
    s["skills"].add_argument("--roots", nargs="+")
    s["fetch"].add_argument("--url", required=True)
    s["fetch"].add_argument("--out", required=True)
    s["fetch"].add_argument("--limit-mb", type=float, default=500)
    s["prep"].add_argument("what", choices=("image", "video"))
    s["prep"].add_argument("--in", dest="src", required=True)
    s["prep"].add_argument("--out", required=True)
    for k in ("slot", "file", "source"):
        s["record"].add_argument("--" + k, required=True)
    for k in ("kind", "prompt", "model", "alt"):
        s["record"].add_argument("--" + k, default="" if k != "kind" else None)
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if not a.cmd:
        p.print_help()
        return 2
    try:
        return run(a)
    except (InputError, ValueError) as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 2
    except (Refused, OSError) as e:                      # права, диск, нет файла человека — отказ, не трассировка
        print("Отказ: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
