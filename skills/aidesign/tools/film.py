#!/usr/bin/env python3
"""«Сайт как фильм» в AI Design: прокрутка ведёт цепочку видеоклипов — план, смета, кадры, кодирование,
страница на своём движке и снимки стыков. Сам ничего не генерирует и не тратит: генерация — ведущим
агентом через подключённые генераторы, media.py и бюджет ad.py media.

    python3 film.py plan --beats 6 --camera fly|walk|locked [--mobile] [--services a,b] [--title T] [--out DIR]
    python3 film.py estimate (--plan film-plan.json | --beats N --camera C [--mobile] [--seams links|blend])
                             --image-cost A --video-cost B [--link-cost C] --unit U [--reserve 0.15]
    python3 film.py models --services a,b [--camera C]          # какие модели держат начальный/конечный кадр
    python3 film.py frames <видео> --first|--last OUT            # настоящий первый/последний кадр
    python3 film.py encode <видео> --desktop|--mobile OUT [--fit crop|pad] [--bg #111111]
    python3 film.py page --plan film-plan.json --out DIR [--force]
    python3 film.py seams --page URL|файл --out DIR [--mobile] [--reduced-motion]

У всех --json. Коды: 0 — хорошо, 1 — нехватка (нет цены, файлов, модели, стык не сошёлся),
2 — ошибка ввода или нет ffmpeg/браузера. Ничего не перезаписывает: занятое имя получает «-2».
По мотивам: oso95/scroll-world references/scrub-engine.js и pipeline.md (MIT, © 2026 cyw) и
MengTo/Skills scroll-world-storytelling (MIT, © 2026 Meng To). Изменено: написано заново.
"""

import argparse
import html
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CAMERAS = {"fly": "полёт: нырок в каждую сцену и перелёт над миром к следующей",
           "walk": "проход: один непрерывный полёт вперёд сквозь все сцены",
           "locked": "фиксированный ракурс: один угол на весь фильм, мир скользит под камерой"}
ROLES = {5: ["Крючок", "Как устроено", "Доказательство", "Итог", "Действие"],
         6: ["Крючок", "Как было", "Как устроено", "Доказательство", "Итог", "Действие"],
         7: ["Крючок", "Как было", "Новое правило", "Как устроено", "Доказательство", "Итог", "Действие"]}
BLEND = ("Ни одна подключённая модель не принимает конечный кадр, поэтому стыки будут перетеканием: "
         "соседние сцены растворяются друг в друге, а не переходят одним пролётом камеры.")
NO_START = ("Ни одна подключённая модель не принимает начальный кадр: сцены не продолжают друг друга, "
            "каждая снимается отдельно, стыки — перетекание.")
FFMPEG_HINT = "ffmpeg не найден — поставить: python3 .aidesign-work/setup.py plan ffmpeg (затем install ffmpeg --yes)"


class InputError(Exception):
    """Код 2."""


class Short(Exception):
    """Нехватка — код 1."""


# ── где что лежит ───────────────────────────────────────────────────────────

def _skill_dir():
    try:
        with open(os.path.join(HERE, "state.js"), encoding="utf-8") as f:
            raw = f.read()
        return json.loads(raw.split("=", 1)[1].strip().rstrip(";")).get("skillDir")
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def find(name, sub, given=None):
    """Файл навыка: рядом с film.py, в папке навыка или в skillDir из state.js (копия в .aidesign-work/)."""
    places = [given] if given else []
    places += [os.path.join(HERE, name), os.path.join(HERE, "..", sub, name)]
    if _skill_dir():
        places.append(os.path.join(_skill_dir(), sub, name))
    for p in places:
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    raise InputError("нет %s — нужна папка навыка (init --skill-dir) или путь явно" % name)


def free(path):
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path, n = "%s-%d%s" % (base, n, ext), n + 1
    return path


# ── модели и кадры (каталог генераторов) ────────────────────────────────────

def models(services, catalog_file=None):
    """Видеомодели подключённых сервисов с полем frames: start_end | start | none."""
    with open(find("генераторы.json", os.path.join("knowledge", "медиа"), catalog_file), encoding="utf-8") as f:
        cat = json.load(f)
    out = []
    for s in cat["services"]:
        if s["id"] in services:
            for m in s.get("models", []):
                if m.get("kind", "video") == "video":
                    out.append(dict(m, service=s["id"], serviceTitle=s["title"]))
    return out


def choose(camera, found):
    """Какая модель и какие стыки: связки (нужен конечный кадр) или перетекание."""
    ends = [m for m in found if m.get("frames") == "start_end"]
    starts = [m for m in found if m.get("frames") in ("start_end", "start")]
    if camera == "fly":
        if ends:
            return {"model": ends[0], "seams": "links", "note": ""}
        return {"model": starts[0] if starts else None, "seams": "blend", "note": BLEND if starts else NO_START}
    if starts:
        return {"model": starts[0], "seams": "chain", "note": ""}
    return {"model": None, "seams": "blend", "note": NO_START}


# ── смета ───────────────────────────────────────────────────────────────────

RESERVE_MIN = 0.15


def counts(beats, camera, seams, mobile, links=None):
    """N кадров + видео: полёт со связками — N нырков и N−1 связок (2N−1); проход и ракурс — N отрезков.
    Телефонные постеры не генерируются: это первые кадры телефонных роликов (frames --first)."""
    if beats not in ROLES:
        raise InputError("битов 5–7: меньше — нет истории, больше — фильм тянется и дорожает")
    if links is None:
        links = beats - 1 if (camera == "fly" and seams == "links") else 0
    video = beats + links
    return {"stills": beats, "clips": beats, "links": links, "videos": video * (2 if mobile else 1),
            "mobile": bool(mobile)}


def counts_of_plan(p):
    """Смета по самому плану, а не по сохранённым в нём числам: сцены, непустые связки, телефон."""
    beats = p.get("beats") or []
    links = sum(1 for x in (p.get("connectors") or []) if x)
    return counts(len(beats), p.get("camera"), None, bool(p.get("mobile")), links=links)


def estimate(c, image_cost, video_cost, link_cost=None, reserve=RESERVE_MIN, unit=""):
    if image_cost is None or video_cost is None:
        raise Short("цены нет: сначала пробный кадр и один ролик, цену — из ответа сервиса, затем estimate с ценами")
    if image_cost <= 0 or video_cost <= 0:
        raise InputError("цена кадра и ролика — больше нуля (из ответа сервиса после пробного кадра)")
    if link_cost is not None and link_cost < 0:
        raise InputError("цена связки не может быть меньше нуля")
    if reserve is None or reserve < RESERVE_MIN:
        raise InputError("запас не меньше %d%%: переделки на стыках бывают всегда" % round(RESERVE_MIN * 100))
    link_cost = video_cost if link_cost is None else link_cost
    per_chain = c["clips"] * video_cost + c["links"] * link_cost
    base = c["stills"] * image_cost + per_chain * (2 if c["mobile"] else 1)
    total = math.ceil(base * (1 + reserve) * 100) / 100
    return {"base": round(base, 2), "reserve": reserve, "total": total, "unit": unit,
            "probe": round(image_cost + video_cost, 2),
            "formula": "%d кадров × %s + (%d роликов × %s + %d связок × %s)%s + %d%% запас"
                       % (c["stills"], image_cost, c["clips"], video_cost, c["links"], link_cost,
                          " × 2 (телефон)" if c["mobile"] else "", round(reserve * 100)),
            "check": "python3 .aidesign-work/ad.py media check --amount %s --unit %s" % (total, unit or "<единица>")}


# ── план ────────────────────────────────────────────────────────────────────

def plan(beats, camera, mobile=False, services=(), title="", catalog_file=None):
    if beats not in ROLES:
        raise InputError("битов 5–7: меньше — нет истории, больше — фильм тянется и дорожает")
    if camera not in CAMERAS:
        raise InputError("камера: fly, walk или locked")
    pick = choose(camera, models(services, catalog_file)) if services else \
        {"model": None, "seams": "links" if camera == "fly" else "chain", "note": "генератор не выбран: media.py detect → --services"}
    items = []
    for i, role in enumerate(ROLES[beats], 1):
        items.append({"id": "b%d" % i, "role": role, "subject": "[ЧТО В СЦЕНЕ %d — впиши]" % i,
                      "title": "[ЗАГОЛОВОК СЦЕНЫ %d — впиши]" % i, "body": "[ФРАЗА СЦЕНЫ %d — впиши]" % i,
                      "still": "film/b%d.webp" % i, "clip": "film/b%d.mp4" % i,
                      "stillMobile": "film/b%d-m.webp" % i if mobile else None,
                      "clipMobile": "film/b%d-m.mp4" % i if mobile else None, "scroll": 1.3, "linger": 0})
    items[0]["scroll"] = items[-1]["scroll"] = 1.6                     # первая и последняя — дольше
    links = ["film/c%d.mp4" % i for i in range(1, beats)] if pick["seams"] == "links" else [None] * (beats - 1)
    return {"version": 1, "title": title or "[НАЗВАНИЕ — впиши]", "lang": "ru", "camera": camera, "mobile": mobile,
            "seams": pick["seams"], "model": pick["model"], "note": pick["note"],
            "theme": {"bg": "#14110f", "ink": "#f3ede4", "accent": "#d0894a"},
            "beats": items, "connectors": links,
            "connectorsMobile": [x and x.replace(".mp4", "-m.mp4") for x in links] if mobile else [],
            "cta": {"label": "[ДЕЙСТВИЕ — впиши]", "href": "#"}, "after": "[ДАЛЬШЕ — обычные разделы сайта]",
            "counts": counts(beats, camera, pick["seams"], mobile, links=sum(1 for x in links if x))}


def plan_md(p):
    c, m = p["counts"], p["model"]
    rows = "\n".join("| %d | %s | %s | %s | %s |" % (i, b["role"], b["subject"], b["clip"], b["scroll"])
                     for i, b in enumerate(p["beats"], 1))
    model = "%s · %s (кадры: %s)" % (m["serviceTitle"], m["title"], m["frames"]) if m else "не выбрана"
    return """# План фильма: {title}

Камера: **{cam}** — {camdesc}.
Стыки: {seams}. Модель: {model}.{note}

| # | Бит | Что в сцене | Клип | Прокрутка (экранов) |
|---|-----|-------------|------|---------------------|
{rows}

## Смета
Кадров {st}, роликов {cl}, связок {li}{mob}; итого видео {vid}. Цены — после пробного кадра:
`python3 .aidesign-work/film.py estimate --plan film-plan.json --image-cost A --video-cost B --unit U`.

## Порядок
1. Пробный кадр и один ролик (бит 1) — посмотреть глазами, узнать цену, записать `ad.py media spend`.
2. Смета → `ad.py media check --amount <итог>`; код 1 — вопрос человеку с суммой.
3. Кадры всех сцен одной преамбулой стиля → ролики по цепочке: каждый следующий начинается с
   настоящего последнего кадра (`film.py frames … --last`); связки — между настоящими кадрами соседей.
4. `film.py encode` (компьютер{mobile_step}) → `film.py page` → `film.py seams` → снимки глазами.
{mobile_note}
Промпты сцен и стыков — по шаблонам `knowledge/медиа/сайт-как-фильм.md` в папке навыка.
""".format(title=p["title"], cam=p["camera"], camdesc=CAMERAS[p["camera"]],
           seams={"links": "связки-пролёты между сценами", "chain": "цепочка, каждый отрезок продолжает предыдущий",
                  "blend": "перетекание (кроссфейд)"}[p["seams"]],
           model=model, note=("\n\n" + p["note"]) if p["note"] else "", rows=rows, st=c["stills"], cl=c["clips"],
           li=c["links"], mob=" ×2 для телефона (своя вертикальная цепочка 9:16)" if c["mobile"] else "",
           vid=c["videos"], mobile_step=" и телефон" if p["mobile"] else "",
           mobile_note=MOBILE_NOTE + "\n" if p["mobile"] else "")


MOBILE_NOTE = ("Телефон: новых картинок не генерируем. Начальный кадр вертикальной цепочки — кадр сцены на "
               "холсте 9:16, постеры `stillMobile` — первые кадры готовых телефонных роликов: "
               "`film.py frames film/b1-m.mp4 --first film/b1-m.webp`.")


# ── ffmpeg ──────────────────────────────────────────────────────────────────

def which_tool(name):
    """Программа в PATH или в AIDESIGN_MEDIA_PATH (так тесты подменяют набор программ)."""
    return shutil.which(name, path=os.environ.get("AIDESIGN_MEDIA_PATH")) if "AIDESIGN_MEDIA_PATH" in os.environ \
        else shutil.which(name)


def ffmpeg(name="ffmpeg"):
    p = which_tool(name)
    if not p:
        raise InputError(FFMPEG_HINT)
    return p


def encoders():
    r = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True, errors="replace")
    return set(re.findall(r"^\s*[VAS][\w.]{5}\s+(\S+)", r.stdout, re.M))


def size_of(src):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", src], capture_output=True, text=True, errors="replace")
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    if not m:
        raise InputError("в %s нет видео" % os.path.basename(src))
    return int(m.group(1)), int(m.group(2))


def _part(out, ext):
    """Временный файл рядом с out (та же папка — переезд на место одной операцией)."""
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".part-", suffix=ext, dir=os.path.dirname(os.path.abspath(out)))
    os.close(fd)
    return tmp


def _ffmpeg_into(args, tmp):
    r = subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin"] + args + [tmp],
                       capture_output=True, text=True, errors="replace", timeout=1800)
    if r.returncode or not os.path.getsize(tmp):
        raise Short("ffmpeg не справился: %s" % (r.stderr or "").strip()[-300:])


def _place(tmp, out):
    dest = free(out)
    mask = os.umask(0)
    os.umask(mask)
    os.chmod(tmp, 0o666 & ~mask)                         # mkstemp даёт 0600 — веб-серверу файл не прочесть
    os.replace(tmp, dest)
    return dest


def _run(args, out):
    """ffmpeg пишет во временный файл рядом, потом — на свободное имя."""
    tmp = _part(out, os.path.splitext(out)[1])
    try:
        _ffmpeg_into(args, tmp)
        return _place(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


WEBP_HINT = "python3 .aidesign-work/setup.py install webp --yes"


def _webp_by_cwebp(args, out, cw):
    """Кадр в PNG через ffmpeg, затем WebP через cwebp (как media.py prep)."""
    png, webp = _part(out, ".png"), _part(out, ".webp")
    try:
        _ffmpeg_into(args, png)
        r = subprocess.run([cw, "-quiet", "-q", "82", png, "-o", webp], capture_output=True, text=True, errors="replace")
        if r.returncode or not os.path.getsize(webp):
            raise Short("cwebp не справился: %s" % (r.stderr or "").strip()[-200:])
        return _place(webp, out)
    finally:
        for p in (png, webp):
            if os.path.exists(p):
                os.remove(p)


def frames(src, which, out):
    """Настоящий первый/последний кадр. WebP без libwebp в ffmpeg — через cwebp; нет и его — PNG с заметкой."""
    if not os.path.isfile(src):
        raise InputError("нет файла %s" % src)
    args = ["-ss", "0", "-i", src, "-frames:v", "1"] if which == "first" else ["-sseof", "-0.5", "-i", src, "-update", "1"]
    args += ["-q:v", "2"]
    notes = []
    if out.lower().endswith(".webp") and "libwebp" not in encoders():
        cw = which_tool("cwebp")
        if cw:
            return {"ok": True, "file": _webp_by_cwebp(args, out, cw), "frame": which, "via": "cwebp", "notes": notes}
        png = os.path.splitext(out)[0] + ".png"
        dest = _run(args, png)
        notes.append("WebP не сделан: в ffmpeg нет libwebp и нет cwebp — кадр сохранён как PNG (%s); в плане фильма "
                     "поправь путь на .png или поставь WebP: %s и повтори" % (os.path.basename(dest), WEBP_HINT))
        return {"ok": True, "file": dest, "frame": which, "via": "png", "notes": notes}
    return {"ok": True, "file": _run(args, out), "frame": which, "via": "ffmpeg", "notes": notes}


def encode(src, target, out, fit="crop", bg="#111111"):
    """Под перемотку: частые ключевые кадры, без звука, faststart; телефон — холст 720×1280 (9:16)."""
    if not os.path.isfile(src):
        raise InputError("нет файла %s" % src)
    w, h = size_of(src)
    notes = []
    if target == "desktop":
        vf, crf, gop = "scale='min(1920,iw)':-2", "20", "8"
    else:
        crf, gop = "23", "4"
        if fit == "pad":
            vf = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=%s" % bg.lstrip("#")
        else:
            vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        if w > h:
            notes.append("исходник горизонтальный: телефонный файл — %s из центра. Это запасной путь; настоящая "
                         "телефонная версия — своя вертикальная цепочка 9:16, скажи это человеку"
                         % ("поля вокруг кадра" if fit == "pad" else "обрезка"))
    dest = _run(["-i", src, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", crf, "-pix_fmt", "yuv420p",
                 "-g", gop, "-keyint_min", gop, "-sc_threshold", "0", "-movflags", "+faststart"], out)
    ow, oh = size_of(dest)
    mb = os.path.getsize(dest) / 1048576
    if mb > 12:
        notes.append("файл %.1f МБ — тяжело для перемотки: выше crf или короче ролик" % mb)
    return {"ok": True, "file": dest, "target": target, "width": ow, "height": oh, "gop": int(gop), "audio": False,
            "faststart": True, "mb": round(mb, 2), "notes": notes}


# ── страница ────────────────────────────────────────────────────────────────

def _beat_html(i, b, last, cta):
    e = html.escape
    tag = "h1" if i == 0 else "h2"
    img = '<img src="%s" alt="%s" width="1280" height="720" loading="%s">' % (
        e(b.get("still") or ""), e(b.get("alt") or b.get("subject") or ""), "eager" if i == 0 else "lazy")
    if b.get("stillMobile"):
        img = '<picture><source media="(max-width: 860px)" srcset="%s">%s</picture>' % (e(b["stillMobile"]), img)
    act = '\n  <a class="sf-action" href="%s">%s</a>' % (e(cta.get("href", "#")), e(cta.get("label", ""))) if last and cta else ""
    return '<article class="sf-beat" id="%s">\n  %s\n  <%s>%s</%s>\n  <p>%s</p>%s\n</article>' % (
        e(b.get("id", "b%d" % (i + 1))), img, tag, e(b.get("title", "")), tag, e(b.get("body", "")), act)


ENGINE_MARK = "AI Design — движок «сайт как фильм»"


def _may_write(path, force, marks, what, same=None):
    """Чужой файл не трогаем никогда; свой (страница фильма, наш движок) — только с --force."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if same is not None and text == same:
        return
    if not all(m in text for m in marks):
        raise Short("%s уже есть и это не %s — не перезаписываю; выбери другую папку --out" % (path, what))
    if not force:
        raise Short("%s уже есть — не перезаписываю (--force, если это прошлая сборка фильма)" % path)


def page(plan_file, out, force=False):
    with open(plan_file, encoding="utf-8") as f:
        p = json.load(f)
    beats = p.get("beats") or []
    if len(beats) < 2:
        raise InputError("в плане меньше двух сцен")
    links = p.get("connectors") or [None] * (len(beats) - 1)
    if len(links) != len(beats) - 1:
        raise InputError("связок должно быть на одну меньше, чем сцен (null — стык перетеканием)")
    index, engine = os.path.join(out, "index.html"), os.path.join(out, "scroll-film.js")
    _may_write(index, force, ("data-film", "sf-config"), "страница фильма")
    with open(find("scroll-film.js", "assets"), encoding="utf-8") as f:
        js = f.read()
    _may_write(engine, force, (ENGINE_MARK,), "движок фильма", same=js)
    os.makedirs(out, exist_ok=True)
    keys = ("clip", "clipMobile", "still", "stillMobile")
    cfg = {"beats": [{k: b.get(k) for k in keys + ("scroll", "linger")} for b in beats], "connectors": links,
           "connectorsMobile": p.get("connectorsMobile") or [], "crossfade": p.get("crossfade", 0.12),
           "blend": p.get("blend", 0.4)}
    theme = dict({"bg": "#14110f", "ink": "#f3ede4", "accent": "#d0894a",
                  "font": 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'}, **(p.get("theme") or {}))
    with open(find("film-page.html", "assets"), encoding="utf-8") as f:
        text = f.read()
    fill = {"lang": p.get("lang", "ru"), "title": html.escape(p.get("title", "")), "after": html.escape(p.get("after", "")),
            "config": json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/"),
            "beats": "\n".join(_beat_html(i, b, i == len(beats) - 1, p.get("cta")) for i, b in enumerate(beats))}
    fill.update({k: theme[k] for k in ("bg", "ink", "accent", "font")})
    for k, v in fill.items():
        text = text.replace("{{%s}}" % k, str(v))
    with open(index, "w", encoding="utf-8") as f:
        f.write(text)
    with open(engine, "w", encoding="utf-8") as f:
        f.write(js)
    used = [b.get(k) for b in beats for k in keys] + list(links) + list(p.get("connectorsMobile") or [])
    used = [u for u in used if u]
    missing = [u for u in used if not os.path.isfile(os.path.join(out, u))]
    weight = {t: round(sum(os.path.getsize(os.path.join(out, u)) for u in used if u.endswith(".mp4")
                           and (u.endswith("-m.mp4") == (t == "mobile")) and u not in missing) / 1048576, 2)
              for t in ("desktop", "mobile")}
    holes = len(re.findall(r"\[[^\]]*— впиши\]", text))
    return {"ok": not missing, "page": index, "missing": missing, "mb": weight, "placeholders": holes}


# ── стыки в браузере ────────────────────────────────────────────────────────

def _browser():
    path = os.path.join(HERE, "browser.py")
    if not os.path.isfile(path):
        raise InputError("нет browser.py рядом с film.py — браузерный модуль нужен для снимков стыков")
    spec = importlib.util.spec_from_file_location("aidesign_browser", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frozen(track):
    """Отрезки, где время видео не растёт с прокруткой (стоп-кадр): три точки отрезка по порядку."""
    spans = {}
    for k, t in enumerate(track):
        spans.setdefault(t.get("span", k // 3), []).append(t)
    bad = []
    for span, pts in sorted(spans.items()):
        pts.sort(key=lambda t: t.get("y", 0))
        times = [t.get("time") for t in pts]
        if None in times or any(b - a < 0.001 for a, b in zip(times, times[1:])):
            bad.append(span)
    return bad


def seams(target, out, mobile=False, reduced=False, timeout=240):
    url = target if re.match(r"^(https?|file):", target) else \
        urllib.parse.urljoin("file:", urllib.request.pathname2url(os.path.abspath(target)))
    base, n = out, 2
    while os.path.isdir(out) and any(x.endswith(".png") for x in os.listdir(out)):   # прошлые снимки не затираем
        out, n = "%s-%d" % (base, n), n + 1
    os.makedirs(out, exist_ok=True)
    br = _browser()
    args = {"url": url, "out": os.path.abspath(out), "mobile": mobile, "reducedMotion": reduced,
            "common": os.path.join(br.SCRIPTS, "common.mjs")}
    try:
        res = br.run(find("film-seams.mjs", "assets"), args, timeout=timeout)
    except br.BrowserError as e:
        raise InputError(str(e))
    sm = res.get("seams", [])
    res["unsettled"] = [s["i"] for s in sm if not (s["before"].get("settled") and s["after"].get("settled"))]
    res["stuck"] = [s["i"] for s in sm if s["after"].get("segment") != (s["before"].get("segment") or 0) + 1]
    res["frozen"] = frozen(res.get("track", []))
    res["ok"] = not (res["unsettled"] or res["stuck"] or res["frozen"] or res.get("errors"))
    res["out"] = os.path.abspath(out)
    return res


# ── командная строка ────────────────────────────────────────────────────────

def _ids(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _say(data, as_json, text):
    print(json.dumps(data, ensure_ascii=False, indent=2) if as_json else text)


def run(a):
    if a.cmd == "plan":
        p = plan(a.beats, a.camera, a.mobile, _ids(a.services), a.title or "", a.catalog)
        os.makedirs(a.out, exist_ok=True)
        jf, mf = os.path.join(a.out, "film-plan.json"), os.path.join(a.out, "film-plan.md")
        if (os.path.exists(jf) or os.path.exists(mf)) and not a.force:
            raise Short("план уже есть в %s — не перезаписываю (--force)" % a.out)
        with open(jf, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        with open(mf, "w", encoding="utf-8") as f:
            f.write(plan_md(p))
        _say(dict(p, files=[jf, mf]), a.json, plan_md(p) + "\nЗаписано: %s, %s" % (jf, mf))
        return 0
    if a.cmd == "estimate":
        if a.plan:
            with open(a.plan, encoding="utf-8") as f:
                c = counts_of_plan(json.load(f))
        elif a.beats and a.camera:
            c = counts(a.beats, a.camera, a.seams, a.mobile)
        else:
            raise InputError("нужен --plan или --beats с --camera")
        try:
            e = estimate(c, a.image_cost, a.video_cost, a.link_cost, a.reserve, a.unit or "")
        except Short as s:
            _say({"counts": c, "total": None, "error": str(s)}, a.json,
                 "Кадров %d, видео %d. %s" % (c["stills"], c["videos"], s))
            return 1
        _say(dict(e, counts=c), a.json, "Смета: %s %s (%s).\nПробный кадр и ролик: %s %s — входит в смету.\n"
             "Проверка бюджета: %s" % (e["total"], e["unit"], e["formula"], e["probe"], e["unit"], e["check"]))
        return 0
    if a.cmd == "models":
        found = models(_ids(a.services), a.catalog)
        pick = choose(a.camera, found)
        lines = ["%s · %s — кадры: %s%s" % (m["serviceTitle"], m["title"], m["frames"],
                                            " (не сверено)" if m.get("unverified") else "") for m in found]
        _say(dict(pick, models=found), a.json, "\n".join(lines or ["видеомоделей с описанием кадров нет"])
             + ("\n" + pick["note"] if pick["note"] else ""))
        return 0 if pick["seams"] != "blend" else 1
    if a.cmd == "frames":
        r = frames(a.video, "first" if a.first else "last", a.out)
        _say(r, a.json, "Кадр: %s%s" % (r["file"], "".join("\n! " + n for n in r["notes"])))
        return 0
    if a.cmd == "encode":
        r = encode(a.video, "desktop" if a.desktop else "mobile", a.out, a.fit, a.bg)
        _say(r, a.json, "Готово: %s — %d×%d, ключевой кадр каждые %d, без звука, faststart, %.2f МБ%s"
             % (r["file"], r["width"], r["height"], r["gop"], r["mb"], "".join("\n! " + n for n in r["notes"])))
        return 0
    if a.cmd == "page":
        r = page(a.plan, a.out, a.force)
        _say(r, a.json, "Страница: %s\nВес видео: компьютер %s МБ, телефон %s МБ. Заглушек текста: %d.%s"
             % (r["page"], r["mb"]["desktop"], r["mb"]["mobile"], r["placeholders"],
                "\nНет файлов: " + ", ".join(r["missing"]) if r["missing"] else ""))
        return 0 if r["ok"] else 1
    if a.cmd == "seams":
        r = seams(a.page, a.out, a.mobile, a.reduced_motion, a.timeout)
        lines = ["стык %d: до — %s, после — %s" % (s["i"], s["before"]["file"], s["after"]["file"]) for s in r.get("seams", [])]
        if r.get("mode") == "reduced-motion":
            lines = ["reduced-motion: видео с src — %d, снимок %s" % (r["still"]["videos"], r["shot"])]
        for k, what in (("unsettled", "видео не встало на кадр: стыки"), ("stuck", "после стыка не следующая сцена: стыки"),
                        ("frozen", "время видео не идёт за прокруткой (стоп-кадр): отрезки")):
            if r.get(k):
                lines.append("! %s %s" % (what, ", ".join(str(x + 1) if k == "frozen" else str(x) for x in r[k])))
        lines += ["! ошибка страницы: %s" % e for e in r.get("errors", [])]
        _say(r, a.json, "\n".join(lines) + "\nСнимки смотри глазами: композиция до и после стыка должна совпадать.")
        return 0 if r["ok"] else 1
    return 2


def main(argv=None):
    p = argparse.ArgumentParser(description="«Сайт как фильм» в AI Design")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("plan")
    c.add_argument("--beats", type=int, required=True)
    c.add_argument("--camera", required=True)
    c.add_argument("--mobile", action="store_true")
    c.add_argument("--services")
    c.add_argument("--title")
    c.add_argument("--out", default=".")
    c.add_argument("--catalog")
    c.add_argument("--force", action="store_true")
    c = sub.add_parser("estimate")
    c.add_argument("--plan")
    c.add_argument("--beats", type=int)
    c.add_argument("--camera", choices=sorted(CAMERAS))
    c.add_argument("--seams", choices=["links", "chain", "blend"], default="links")
    c.add_argument("--mobile", action="store_true")
    for k in ("--image-cost", "--video-cost", "--link-cost"):
        c.add_argument(k, type=float)
    c.add_argument("--reserve", type=float, default=0.15)
    c.add_argument("--unit")
    c = sub.add_parser("models")
    c.add_argument("--services", required=True)
    c.add_argument("--camera", choices=sorted(CAMERAS), default="fly")
    c.add_argument("--catalog")
    c = sub.add_parser("frames")
    c.add_argument("video")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--first", action="store_true")
    g.add_argument("--last", action="store_true")
    c.add_argument("out")
    c = sub.add_parser("encode")
    c.add_argument("video")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--desktop", action="store_true")
    g.add_argument("--mobile", action="store_true")
    c.add_argument("out")
    c.add_argument("--fit", choices=["crop", "pad"], default="crop")
    c.add_argument("--bg", default="#111111")
    c = sub.add_parser("page")
    c.add_argument("--plan", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--force", action="store_true")
    c = sub.add_parser("seams")
    c.add_argument("--page", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--mobile", action="store_true")
    c.add_argument("--reduced-motion", action="store_true")
    c.add_argument("--timeout", type=float, default=240)
    for s in sub.choices.values():
        s.add_argument("--json", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit as err:
        return 2 if err.code else 0
    if not a.cmd:
        p.print_help()
        return 2
    try:
        return run(a)
    except InputError as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 2
    except Short as e:
        print(str(e), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as e:
        print("Ошибка ввода: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
