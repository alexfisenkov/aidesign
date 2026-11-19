#!/usr/bin/env python3
# Происхождение: основано на AISpa 1.0.2 (MIT), tools/ap.py. Изменено: поля и команды прогона дизайна
# (референсы, темы интервью, круги превью, направление), папка .aidesign-work.
"""Учёт прогона AI Design: состояние, панель, сервер — одной командой на событие.

Агент не правит .aidesign-work/state.js руками. Каждое событие прогона — один вызов:

    python3 .aidesign-work/ad.py init --slug S --title "…" --mode interview --entry new --skill-dir /abs
    python3 .aidesign-work/ad.py stage refs                    # открыть этап (прошлые закроются сами)
    python3 .aidesign-work/ad.py stage interview skip --note "референсов хватило"
    python3 .aidesign-work/ad.py set questions=rounds
    python3 .aidesign-work/ad.py ask refs --note "пришли картинки или ссылки"   # ждём человека
    python3 .aidesign-work/ad.py answered
    python3 .aidesign-work/ad.py ref add --path референсы/1.png --kind image --note "тёплый беж, крупный шрифт"
    python3 .aidesign-work/ad.py ref note --i 1 --note "…"
    python3 .aidesign-work/ad.py theme add --id tone --title "Тон"
    python3 .aidesign-work/ad.py theme set --id tone --status decided
    python3 .aidesign-work/ad.py round new                     # новый круг превью
    python3 .aidesign-work/ad.py round option --id a --title "Редакционный" --src rounds/01/a.html
                                 # снимки a-1280.png и a-390.png рядом (shots.py) подхватит сам
    python3 .aidesign-work/ad.py round feedback --text "в A нравится шрифт, в C цвет"
    python3 .aidesign-work/ad.py round choose --id b           # или none — ничего не подошло
    python3 .aidesign-work/ad.py round refine --id a           # новый круг: доработать вариант A
    python3 .aidesign-work/ad.py direction set --name "…" --summary "…" --file DESIGN.md
    python3 .aidesign-work/ad.py check --findings 7 --fixed 7
    python3 .aidesign-work/ad.py add report "…"  |  add assumptions "…"
    python3 .aidesign-work/ad.py backup add --id ID --reason "до" --bytes 2048   # после backup.py create
    python3 .aidesign-work/ad.py figma set --url https://www.figma.com/design/… --mode free|paid
    python3 .aidesign-work/ad.py toolkit set --missing ffmpeg --installed node,playwright --skipped figma
    python3 .aidesign-work/ad.py media budget --limit 100 --unit кредитов      # одна сумма на прогон
    python3 .aidesign-work/ad.py media check --amount 12      # код 0 — в бюджете, 1 — выйдет за сумму или бюджета нет
    python3 .aidesign-work/ad.py media spend --service higgsfield --amount 12 --item "фон героя"
    python3 .aidesign-work/ad.py media connected --ids higgsfield,magnific   # что подключено (media.py detect)
    python3 .aidesign-work/ad.py media sources --set own|generate|mixed|code|placeholder
    python3 .aidesign-work/ad.py media recorded --slot hero    # зовёт media.py record сам: опись изменилась
    python3 .aidesign-work/ad.py finish --result "Лендинг собран в стиле «тёплая редакция»"
    python3 .aidesign-work/ad.py                               # поднять сервер и синхронизировать

После каждой команды: updatedAt = сейчас (и метка в журнале beats), строка в ленте log,
пройденные этапы закрыты, снимок вписан в dashboard.html, сервер жив. После событий, которые
меняют проект (direction, backup, figma, toolkit, media, stage build|check|handoff done, finish),
подраздел «Сейчас» блока aidesign в AGENTS.md / CLAUDE.md переписывается сам (rules.py). Время ставит сам
скрипт, с секундами и поясом, — агент его не пишет никогда.
Значение, которое начинается с «--», передаётся через знак равенства: --note=--срочно.

Флаги: --check-update (сверить версию навыка с GitHub), --no-serve, --stop (погасить сервер сейчас).
Сервер панели отдаёт файлы кусками (HTTP Range) — без этого видео по прокрутке не перематывается.
Тот же сервер для собранного сайта, из его папки (на переднем плане, Ctrl+C — стоп):
    python3 .aidesign-work/ad.py --serve-http 8000 --directory .
Работает на macOS, Linux и Windows (в том числе из Git Bash).
"""

import datetime as dt
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

for _s in (sys.stdout, sys.stderr):                       # cp1251-консоль Windows
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

A = os.path.dirname(os.path.abspath(__file__))          # .aidesign-work этого проекта
ROOT = os.path.dirname(A)
STATE = os.path.join(A, "state.js")
PAGE = os.path.join(A, "dashboard.html")
INDEX = os.path.join(A, "index.html")
README = os.path.join(A, "README.md")
PIDF = os.path.join(A, "serve.pid")
LOG = os.path.join(A, "serve.log")
STOPF = os.path.join(A, "serve.stop")                    # отложенная остановка ещё в силе (её метка)
STOPPING = os.path.join(A, "serve.stopping")             # остановка уже гасит сервер
WORK = os.path.basename(A) or ".aidesign-work"
BEGIN, END = "/*STATE-BEGIN*/", "/*STATE-END*/"
WIN = os.name == "nt"
REPO = "alexfisenkov/aidesign"
REMOTE_SKILL = "https://raw.githubusercontent.com/%s/main/skills/aidesign/SKILL.md" % REPO
VERSION = 1
try:                                                     # переменная — только для тестов
    STOP_DELAY = max(0, int(os.environ.get("AIDESIGN_STOP_DELAY", "12")))
except ValueError:
    STOP_DELAY = 12
BEATS_KEPT = 2000
LOG_KEPT = 300
WAIT_KINDS = ("refs", "interview", "previews", "action", "stop")
# Команды, которые значат «работа пошла дальше»: ожидание человека ими закрывается,
# даже если `answered` забыли.
MOVES_ON = {"stage", "round", "direction", "check", "finish"}
MODES = ("auto", "important", "interview")
QUESTION_FORMS = ("rounds", "one")
QUESTION_WORDS = {
    "round": "rounds", "раундами": "rounds", "пачкой": "rounds", "по несколько": "rounds",
    "по одному": "one", "по-одному": "one", "одному": "one", "one at a time": "one",
}
ENTRIES = ("new", "existing")
ORDER = ["preflight", "refs", "interview", "previews", "build", "check", "handoff"]
# Этап, чей результат лежит на диске, пройден — даже если его забыли отметить.
ARTIFACT = {"refs": "refs.md", "interview": "interview.md", "previews": "rounds/*/*.html"}
LISTS = {"report", "assumptions"}
REF_KINDS = ("image", "screenshot", "url", "text")
THEME_STATUSES = ("wait", "asked", "answered", "decided")
OPTION_IDS = ("a", "b", "c")
FULL_ROUND = len(OPTION_IDS)
TOOLS = ("check.py", "setup.py", "backup.py", "scaffold.py", "designsystem.py", "rules.py",
         "shots.py", "media.py",
         "check_parse.py", "check_tailwind.py", "check_dom.py", "check_cascade.py", "check_boxes.py",
         "check_parity.py", "check_browser.py",            # части check.py (импортирует их из своей папки)
         "browser.py", "extract.py", "pick.py", "film.py")  # копии рядом с ad.py
MEDIA_CATALOG = os.path.join("knowledge", "медиа", "генераторы.json")   # каталог генераторов для media.py
# Папки целиком: скрипты браузерного модуля (рядом с browser.py) и справочник (pick.py ищет его рядом с собой).
TOOL_DIRS = ((os.path.join("tools", "browser"), "browser"), (os.path.join("knowledge", "справочник"), "справочник"))
SHOT_KEYS = (("shot1280", 1280), ("shot390", 390))       # снимки превью: компьютер и телефон
FIGMA_MODES = ("free", "paid")
MEDIA_SOURCES = ("own", "generate", "mixed", "code", "placeholder")


def now():
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def die(msg):
    print("ошибка: " + msg)
    sys.exit(1)


# ── состояние ───────────────────────────────────────────────────────────────

def read_state():
    try:
        raw = open(STATE, encoding="utf-8").read()
    except FileNotFoundError:
        return None
    body = raw.split("=", 1)[1] if "=" in raw.split("\n", 1)[0] else raw
    try:
        return json.loads(body.strip().rstrip(";"))
    except json.JSONDecodeError as e:
        die("state.js не разбирается (строка %d: %s) — перезапиши его командой init "
            "или поправь строку" % (e.lineno, e.msg))


def save(state):
    state["rev"] = (state.get("rev") or 0) + 1        # панель перерисовывается по нему
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.STATE =\n" + json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, STATE)


def beat(state):
    """Журнал пульса: каждое событие оставляет метку. updatedAt перезаписывается,
    и без журнала панель знала о прошлых событиях, только если сама их видела, —
    уснул экран или упал сервер, и рабочее время между редкими метками
    обрезалось как простой."""
    beats = state.setdefault("beats", [])
    if state["updatedAt"] not in beats:
        beats.append(state["updatedAt"])
    del beats[:-BEATS_KEPT]


def log(state, event, **kw):
    """Лента событий для панели: что случилось, словами страницы, а не агента."""
    entry = {"t": state["updatedAt"], "k": event}
    entry.update({k: v for k, v in kw.items() if v not in (None, "", [])})
    state.setdefault("log", []).append(entry)
    del state["log"][:-LOG_KEPT]


def close_wait(state):
    """Ожидание человека кончилось: интервал уходит в waits — часы панели
    его не считают, это не работа."""
    w = state.get("waiting")
    if not w:
        return
    state.setdefault("waits", []).append({"kind": w.get("kind"), "from": w.get("since"),
                                          "to": state["updatedAt"]})
    state["waiting"] = None
    log(state, "answered", kind=w.get("kind"))


def run_dir(state):
    return os.path.join(A, state.get("dir") or "")


def choice_of(v, allowed, what, words=None):
    x = str(v or "").strip().lower()
    x = (words or {}).get(x, x)
    if x not in allowed:
        die("%s: %s, а не «%s»" % (what, " | ".join(allowed), v))
    return x


def mode_of(v):
    return choice_of(v, MODES, "режим")


def questions_of(v):
    return choice_of(v, QUESTION_FORMS, "вопросы (rounds — раундами, one — по одному)", QUESTION_WORDS)


def entry_of(v):
    return choice_of(v, ENTRIES, "вход (new — новый сайт, existing — готовый сайт)")


def fresh_state(a):
    t = now()
    return {
        "version": VERSION,
        "slug": a["slug"], "dir": "%s-%s--wip" % (t[:10], a["slug"]),
        "title": a.get("title") or a["slug"],
        "mode": mode_of(a.get("mode") or "interview"),
        "questions": questions_of(a.get("questions") or "one"),
        "entry": entry_of(a.get("entry") or "new"),
        "skillDir": a.get("skill-dir"), "skillVersion": skill_version(a.get("skill-dir")),
        "startedAt": t, "updatedAt": t, "finishedAt": None,
        "stages": [{"id": "preflight", "status": "active", "startedAt": t}]
                  + [{"id": s, "status": "pending"} for s in ORDER[1:]],
        "waiting": None, "waits": [], "beats": [t], "log": [],
        "refs": [], "themes": [], "rounds": [],
        "direction": None, "check": None, "report": [], "assumptions": [],
        "result": None, "rev": 0,
        "backups": [], "figma": None, "toolkit": None, "media": fresh_media(),
    }


def fresh_media():
    return {"budget": None, "spent": [], "connected": [], "sources": None}


# ── этапы ───────────────────────────────────────────────────────────────────

def stage(state, sid):
    for s in state.get("stages") or []:
        if s.get("id") == sid:
            return s
    s = {"id": sid, "status": "pending"}
    state.setdefault("stages", []).append(s)
    return s


def close_passed(state):
    """Инвариант: раньше открытого этапа не бывает другого открытого. Прошлый
    закрывается временем открытия ближайшего следующего. Этап, который прогон
    проскочил, не отметив, закрывается, если его файл лежит на диске.
    skipped и failed — осознанные состояния, их не трогаем."""
    rank = {v: i for i, v in enumerate(ORDER)}
    stages = [s for s in state.get("stages") or [] if s.get("id") in rank]
    live = [s for s in stages if s.get("status") == "active"]
    closed = []
    for s in live:
        later = sorted(o["startedAt"] for o in live
                       if rank[o["id"]] > rank[s["id"]] and o.get("startedAt"))
        if later:
            s["status"], s["finishedAt"] = "done", later[0]
            closed.append("%s закрыт (%s)" % (s["id"], later[0][11:19]))
    reached = [rank[s["id"]] for s in stages if s.get("status") in ("active", "done")]
    if not reached:
        return closed
    edge = max(reached)
    for s in stages:
        art = ARTIFACT.get(s["id"])
        if s.get("status") != "pending" or rank[s["id"]] >= edge or not art or not state.get("dir"):
            continue
        if glob.glob(os.path.join(run_dir(state), art)):
            nxt = [o["startedAt"] for o in stages if rank[o["id"]] > rank[s["id"]] and o.get("startedAt")]
            when = min(nxt) if nxt else state.get("updatedAt")
            s["status"], s["startedAt"], s["finishedAt"] = "done", s.get("startedAt") or when, when
            closed.append("%s отмечен пройденным по файлу %s" % (s["id"], art))
    return closed


def audit(state):
    out = []
    rank = {v: i for i, v in enumerate(ORDER)}
    stages = state.get("stages") or []
    live = [rank[s["id"]] for s in stages if s.get("status") == "active" and s.get("id") in rank]
    if live:
        for s in stages:
            if s.get("status") == "pending" and rank.get(s.get("id"), 99) < max(live):
                out.append("этап %s пропущен в учёте: был — `stage %s done`, не было — `stage %s skip "
                           "--note причина`. Это бухгалтерия, не расследуй" % ((s["id"],) * 3))
    return out


# ── страница и сервер ───────────────────────────────────────────────────────

def write_snapshot(state):
    try:
        page = open(PAGE, encoding="utf-8").read()
    except FileNotFoundError:
        return "страницы нет — перекопируй dashboard.html из навыка (или init --skill-dir)"
    i, j = page.find(BEGIN), page.find(END)
    if i < 0 or j < 0:
        return "страница без маркеров снимка — перекопируй dashboard.html из навыка"
    payload = "window.STATE=" + json.dumps(state, ensure_ascii=False).replace("</", "<\\/") + ";"
    new = page[: i + len(BEGIN)] + payload + page[j:]
    targets = [PAGE] + ([INDEX] if os.path.isfile(INDEX) and not os.path.islink(INDEX) else [])
    for path in targets:
        try:
            old = open(path, encoding="utf-8").read()
        except OSError:
            old = None
        if new != old:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(new)
            os.replace(tmp, path)
    return "панель обновлена"


def install_page(skill):
    """Шаблон панели и примеры работ — из папки навыка в .aidesign-work/.
    index.html — та же страница, чтобы корень сервера не показывал листинг."""
    notes = []
    tpl = os.path.join(skill, "phases", "dashboard-template.html") if skill else ""
    if tpl and os.path.isfile(tpl):
        shutil.copyfile(tpl, PAGE)
        if not os.path.lexists(INDEX):
            try:
                os.symlink("dashboard.html", INDEX)
            except (OSError, NotImplementedError, AttributeError):
                shutil.copyfile(PAGE, INDEX)
    elif not os.path.isfile(PAGE):
        notes.append("! шаблона панели нет — нужен --skill-dir с phases/dashboard-template.html")
    ex = os.path.join(skill, "examples") if skill else ""
    if ex and os.path.isdir(ex):
        shutil.copytree(ex, os.path.join(A, "examples"), dirs_exist_ok=True)
        notes.append("примеры работ: %s/examples/" % WORK)
    tools = os.path.join(skill, "tools") if skill else ""
    copied = [t for t in TOOLS if tools and os.path.isfile(os.path.join(tools, t))]
    for t in copied:
        shutil.copyfile(os.path.join(tools, t), os.path.join(A, t))
    cat = os.path.join(skill, MEDIA_CATALOG) if skill else ""
    if cat and os.path.isfile(cat):
        shutil.copyfile(cat, os.path.join(A, os.path.basename(cat)))
        copied.append(os.path.basename(cat))
    for src, dst in TOOL_DIRS:
        path = os.path.join(skill, src) if skill else ""
        if path and os.path.isdir(path):
            shutil.copytree(path, os.path.join(A, dst), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            copied.append(dst + "/")
    if copied:
        notes.append("инструменты: %s" % ", ".join("%s/%s" % (WORK, t) for t in copied))
    return notes


def _run(args):
    # ps в локали C показывает кириллицу в пути «M-PM-…» — и сервер не узнаётся: просим UTF-8.
    env = dict(os.environ, LC_CTYPE="UTF-8" if sys.platform == "darwin" else "C.UTF-8")
    env.pop("LC_ALL", None)
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10, env=env,
                              encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _ps(script):
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def cmdline(pid):
    if WIN:
        return _ps("(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine" % int(pid)).strip()
    return _run(["ps", "-p", str(pid), "-o", "command="]).strip()


def processes():
    out = []
    if WIN:
        text = _ps("Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
                   "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
        for line in text.splitlines():
            num, _, cmd = line.partition("\t")
            if num.strip().isdigit():
                out.append((int(num), cmd))
    else:
        for line in _run(["ps", "-Ao", "pid=,command="]).splitlines():
            num, _, cmd = line.strip().partition(" ")
            if num.isdigit():
                out.append((int(num), cmd))
    return out


def _norm(path):
    return os.path.normcase(os.path.normpath(path)).replace("\\", "/")


_OURS = re.compile(r"--directory\s+\"?" + re.escape(_norm(A)) + r"\"?(?=\s|$)")


def is_ours(cmd):
    """Сервер этого проекта — и только он: наш `--serve-http` (или прежний `-m http.server`)
    и ровно наш --directory. Узко намеренно: широкая проверка уже убивала чужие серверы."""
    c = cmd.replace("\\", "/")
    c = c.lower() if WIN else c
    return bool(re.search(r"(-m\s+http\.server|--serve-http)\b", c)) and bool(_OURS.search(c))


def server_id(directory, pid):
    """Метка сервера в заголовке ответа: его pid и отпечаток папки. По ней остановка узнаёт
    свой сервер, даже когда ps показывает путь с кириллицей не как есть (локаль C, Windows)."""
    import hashlib
    path = _norm(os.path.realpath(directory)).encode("utf-8", "surrogateescape")
    return "%d %s" % (int(pid), hashlib.sha1(path).hexdigest()[:16])


def answers_as_ours(port, pid):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/dashboard.html" % port, timeout=2) as r:
            return r.headers.get("X-AIDesign-Server") == server_id(A, pid)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def kill(pid):
    try:
        os.kill(int(pid), 15)
    except (OSError, ValueError):
        pass


def recorded():
    try:
        port, pid = open(PIDF, encoding="utf-8").read().split()
        return int(port), int(pid)
    except (OSError, ValueError):
        return None, None


def http_ok(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/dashboard.html" % port, timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def free_port(prefer):
    """Прежний порт — в первую очередь: открытая вкладка опрашивает именно его и
    оживает сама, когда сервер вернулся. SO_REUSEADDR — чтобы порт в TIME_WAIT
    не считался занятым. На Windows флаг значит другое — там без него."""
    for p in ([prefer] if prefer else []) + [0]:
        s = socket.socket()
        if not WIN:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", p))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return None


def kill_orphans(keep=None):
    n = 0
    for pid, cmd in processes():
        if pid not in (keep, os.getpid()) and is_ours(cmd):
            kill(pid)
            n += 1
    return n


def _detached():
    if WIN:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}


def serve(state):
    """Сервер нужен и сданному прогону: превью кругов и примеры видны только по http.
    Вызов, который просит сервер, отменяет отложенную остановку от finish."""
    try:
        os.remove(STOPF)
    except OSError:
        pass
    wait_stopping()
    port, pid = recorded()
    if os.environ.get("SSH_CONNECTION") or os.environ.get("CI"):
        return "удалённая сессия — без сервера, панель: %s" % PAGE
    if port and pid and http_ok(port) and is_ours(cmdline(pid)):
        return "http://localhost:%d/dashboard.html" % port
    kill_orphans()
    port = free_port(port)
    if not port:
        return "порт не нашёлся — панель открывается файлом: %s" % PAGE
    try:
        with open(LOG, "a", encoding="utf-8") as lf:
            srv = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--serve-http", str(port),
                                    "--directory", A],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=lf, **_detached())
    except OSError as e:
        return "сервер не запустился (%s) — панель открывается файлом: %s" % (e, PAGE)
    for _ in range(10):
        if http_ok(port):
            with open(PIDF, "w", encoding="utf-8") as f:
                f.write("%d %d\n" % (port, srv.pid))
            return "сервер поднят: http://localhost:%d/dashboard.html" % port
        try:
            srv.wait(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            continue
    srv.terminate()
    return "сервер не ответил — панель открывается файлом: %s" % PAGE


def wait_stopping(limit=10.0):
    """Остановка уже гасит сервер — его адрес отдавать нельзя: ждём, пока она кончит,
    и поднимаем новый. Метка старше минуты — от упавшей остановки, её не ждём."""
    end = time.time() + limit
    while time.time() < end:
        try:
            if time.time() - os.path.getmtime(STOPPING) > 60:
                return
        except OSError:
            return
        time.sleep(0.2)


def stop_now(token=None):
    """Гасит сервер, только если отложенная остановка всё ещё его, а не чья-то новая:
    в serve.stop лежит метка той остановки, что поставлена последней. Захват —
    переименованием serve.stop в serve.stopping: serve, пришедший раньше, уже убрал
    serve.stop, и остановка отменена; пришедший позже видит serve.stopping и ждёт."""
    time.sleep(STOP_DELAY)
    try:
        mark = open(STOPF, encoding="utf-8").read().strip()
    except OSError:                        # сервер снова попросили — остановка отменена
        return
    if token and mark != token:            # остановку поставили заново — та и погасит в свой срок
        return
    try:
        os.replace(STOPF, STOPPING)
    except OSError:
        return
    try:
        _stop_server()
    finally:
        try:
            os.remove(STOPPING)
        except OSError:
            pass


def stop_explicit():
    """`ad.py --stop`: человек просит погасить сейчас, а не через STOP_DELAY. Отложенная остановка
    от finish снимается; метка serve.stopping держит голый вызов, пока сервер гаснет."""
    try:
        os.remove(STOPF)
    except OSError:
        pass
    port = recorded()[0]
    with open(STOPPING, "w", encoding="utf-8") as f:
        f.write("ad.py --stop\n")
    try:
        _stop_server()
    finally:
        try:
            os.remove(STOPPING)
        except OSError:
            pass
    if port and http_ok(port):
        return "сервер не погас: порт %d ещё отвечает — закрой его процесс вручную" % port
    return "сервер погашен"


def gone(pid, port, limit=3.0):
    """Процесс завершился и порт не отвечает — ждём до limit секунд."""
    end = time.time() + limit
    while time.time() < end:
        alive = False
        if pid and not WIN:
            try:
                os.kill(int(pid), 0)
                alive = True
            except OSError:
                pass
        if not alive and not (port and http_ok(port)):
            return True
        time.sleep(0.1)
    return False


def _stop_server():
    port, pid = recorded()
    if pid and (is_ours(cmdline(pid)) or (port and answers_as_ours(port, pid))):
        kill(pid)
        if not gone(pid, port) and not WIN:
            try:
                os.kill(int(pid), 9)                 # SIGTERM не дошёл — добиваем свой же процесс
            except OSError:
                pass
            gone(pid, port, 1.0)
    kill_orphans()
    try:
        os.remove(LOG)
    except OSError:
        pass
    # Порт запоминается без процесса («порт 0»): голый ad.py поднимет панель на
    # прежнем адресе, и открытая вкладка оживёт сама, если порт ещё свободен.
    try:
        if port:
            with open(PIDF, "w", encoding="utf-8") as f:
                f.write("%d 0\n" % port)
        else:
            os.remove(PIDF)
    except OSError:
        pass


def stop_later():
    """Гасит сервер через STOP_DELAY секунд из отдельного процесса: страница
    опрашивает state.js раз в 10 секунд и должна успеть забрать финал.
    Голый вызов ad.py до срока отменяет остановку (serve убирает serve.stop)."""
    token = "%s-%d-%d" % (now(), os.getpid(), time.time_ns() % 1000000)
    with open(STOPF, "w", encoding="utf-8") as f:
        f.write(token + "\n")
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--stop-now", token],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **_detached())
    return "сервер погаснет через %d с" % STOP_DELAY


# ── http-сервер с Range: панель и показ собранного сайта ────────────────────

def byte_span(header, size):
    """Один диапазон из Range: (начало, конец включительно); "all" — отдать файл целиком
    (несколько диапазонов, другая единица); None — диапазон неверный или за концом файла (416)."""
    unit, _, spec = (header or "").strip().partition("=")
    if unit.strip().lower() != "bytes":
        return "all"
    if "," in spec:
        return "all"
    m = re.match(r"^\s*(\d*)\s*-\s*(\d*)\s*$", spec)
    if not m or not (m.group(1) or m.group(2)) or size <= 0:
        return None
    if not m.group(1):
        n = int(m.group(2))
        return (max(0, size - n), size - 1) if n else None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if start >= size or end < start:
        return None
    return start, min(end, size - 1)


def range_handler():
    """Обработчик на основе SimpleHTTPRequestHandler: файлы кусками (206, Accept-Ranges,
    Content-Range). Без этого браузер не перематывает видео — seekable пуст, currentTime стоит."""
    import http.server

    class RangeHandler(http.server.SimpleHTTPRequestHandler):
        extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{
            ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
            ".avif": "image/avif", ".webp": "image/webp", ".svg": "image/svg+xml", ".glb": "model/gltf-binary",
            ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
            ".wasm": "application/wasm", ".mp3": "audio/mpeg", ".wav": "audio/wav"})
        span = None
        ident = ""

        def end_headers(self):
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-AIDesign-Server", self.ident)
            super().end_headers()

        def send_head(self):
            self.span = None
            rng = self.headers.get("Range")
            path = self.translate_path(self.path)
            if not rng or not os.path.isfile(path) or self.path.split("?")[0].endswith("/"):
                return super().send_head()
            try:
                f = open(path, "rb")
            except OSError:
                return super().send_head()
            st = os.fstat(f.fileno())
            span = byte_span(rng, st.st_size)
            if span == "all":
                f.close()
                return super().send_head()
            if span is None:
                f.close()
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % st.st_size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            start, end = span
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, st.st_size))
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Last-Modified", self.date_time_string(st.st_mtime))
            self.end_headers()
            f.seek(start)
            self.span = end - start + 1
            return f

        def copyfile(self, source, outputfile):
            try:
                if self.span is None:
                    return super().copyfile(source, outputfile)
                left = self.span
                while left > 0:
                    chunk = source.read(min(1 << 16, left))
                    if not chunk:
                        break
                    outputfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass                             # браузер сам обрывает лишние куски при перемотке

    return RangeHandler


def serve_http_cli(argv):
    """`ad.py --serve-http PORT [--directory DIR]` — сервер с Range на 127.0.0.1, на переднем плане.
    Им же ad.py поднимает панель; собранный сайт показывают так же, из папки сайта."""
    import functools
    import http.server
    _, opt = parse_args(argv[1:])
    try:
        port = int(argv[0]) if argv else 8000
    except ValueError:
        print("порт — число: ad.py --serve-http 8000 [--directory папка-сайта]", file=sys.stderr)
        return 2
    folder = os.path.abspath(text_opt(opt, "directory") or os.getcwd())
    if not os.path.isdir(folder):
        print("папки %s нет" % folder, file=sys.stderr)
        return 2
    handler = range_handler()
    handler.ident = server_id(folder, os.getpid())
    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(handler, directory=folder))
    except OSError as e:
        print("порт %d занят или недоступен (%s) — возьми другой" % (port, e), file=sys.stderr)
        return 1
    print("Сервер с Range: http://localhost:%d/ — папка %s; остановить: Ctrl+C" % (httpd.server_address[1], folder),
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


# ── версия навыка ───────────────────────────────────────────────────────────

_VER = re.compile(r"^\s*version:\s*[\"']?(\d+(?:\.\d+)*)", re.M)


def _version_str(text):
    """metadata.version из шапки SKILL.md строкой, как написано: «0.1.0»."""
    m = _VER.search(text.split("\n---", 1)[0] if text.startswith("---") else "")
    return m.group(1) if m else None


def _version(text):
    v = _version_str(text)
    return tuple(int(x) for x in v.split(".")) if v else None


def skill_version(skill_dir):
    """SKILL.md из --skill-dir, иначе рядом с ad.py (в пакете ad.py лежит в tools/).
    Копия в .aidesign-work/ без --skill-dir версии не знает — null, а не выдумка."""
    here = os.path.dirname(os.path.abspath(__file__))
    places = [skill_dir] if skill_dir else []
    places.append(here)
    if os.path.basename(here) == "tools":
        places.append(os.path.dirname(here))
    for d in places:
        try:
            with open(os.path.join(d, "SKILL.md"), encoding="utf-8") as f:
                v = _version_str(f.read())
        except OSError:
            continue
        if v:
            return v
    return None


def check_update(state):
    """Строка, если навык новее. Без сети — молчит. AIDESIGN_NO_UPDATE_CHECK=1 выключает."""
    if os.environ.get("AIDESIGN_NO_UPDATE_CHECK"):
        return None
    skill = state.get("skillDir") or ""
    try:
        local = _version(open(os.path.join(skill, "SKILL.md"), encoding="utf-8").read())
    except OSError:
        return None
    try:
        with urllib.request.urlopen(REMOTE_SKILL, timeout=3) as r:
            remote = _version(r.read(65536).decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not remote or (local and remote <= local):
        return None
    home = _norm(os.path.expanduser("~"))
    flag = " -g" if _norm(skill).startswith(home + "/.") else ""
    v = lambda t: ".".join(map(str, t))
    return ("вышла версия AI Design %s (у тебя %s): npx skills update aidesign%s · "
            "что нового — github.com/%s/blob/main/CHANGELOG.md"
            % (v(remote), v(local) if local else "без номера", flag, REPO))


# ── реестр прогонов (.aidesign-work/README.md) ───────────────────────────────

README_TEXT = """# Как читать эту папку

- `dashboard.html` — панель AI Design: этапы, время, референсы, темы интервью,
  три превью текущего круга и история кругов. Превью видны только через сервер —
  открывай адрес http://localhost:…, который назвал агент.
  `index.html` рядом — та же страница под другим именем.
- `<дата>-<проект>/` — папка одного прогона. Суффикс `--wip` значит «ещё делается».
  Внутри: `brief.md` (твои слова), `refs.md`, `vkus.md`, `interview.md`,
  `rounds/NN/` — превью кругов, `direction.md`, `report.md`.
- `examples/` — примеры работ AI Design для вкладки «Примеры работ».
- `backups/` — копии проекта (`backup.py list`); `<id>-лишнее/` — файлы, унесённые при откате.
  Копии не удаляются без твоего слова.

Если прогон прервался — скажи агенту «продолжи AI Design», он поднимет состояние отсюда.

## Прогоны

| Начат | Папка | Статус | Итог |
|---|---|---|---|
"""


def register_row(state, status, result):
    d = state.get("dir") or ""
    base = re.sub(r"--wip$", "", d)
    try:
        text = open(README, encoding="utf-8").read()
    except OSError:
        text = README_TEXT
    if "## Прогоны" not in text:
        text = text.rstrip("\n") + "\n\n## Прогоны\n\n| Начат | Папка | Статус | Итог |\n|---|---|---|---|\n"
    row = "| %s | `%s` | %s | %s |" % (d[:10], d, status, result or "—")
    lines = text.splitlines()
    hit = [i for i, l in enumerate(lines) if l.startswith("|") and ("`%s`" % base in l or "`%s--wip`" % base in l)]
    if hit:
        lines[hit[-1]] = row
    else:
        lines.append(row)
    with open(README, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def git_mv(src, dst):
    if subprocess.run(["git", "-C", A, "mv", src, dst], capture_output=True).returncode == 0:
        return True
    try:
        os.rename(os.path.join(A, src), os.path.join(A, dst))
        return True
    except OSError:
        return False


def ensure_gitignore():
    g = os.path.join(ROOT, ".gitignore")
    line = "%s/serve.*" % WORK
    try:
        text = open(g, encoding="utf-8").read()
    except OSError:
        text = ""
    if re.search(r"^" + re.escape(line), text, re.M):
        return
    with open(g, "a", encoding="utf-8") as f:
        f.write(("" if not text or text.endswith("\n") else "\n") + line + "\n")


# ── команды ─────────────────────────────────────────────────────────────────

def parse_args(argv):
    pos, opt = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and "=" in a:
            key, _, val = a[2:].partition("=")
            opt[key] = val
        elif a.startswith("--"):
            key = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                opt[key] = argv[i + 1]
                i += 2
                continue
            opt[key] = True
        else:
            pos.append(a)
        i += 1
    return pos, opt


def text_opt(opt, key):
    v = opt.get(key)
    return v if isinstance(v, str) else None


def need(opt, key, usage):
    v = text_opt(opt, key)
    if not v:
        die("нужно --%s: %s" % (key, usage))
    return v


def cmd_init(opt):
    if not opt.get("slug") or opt["slug"] is True:
        die("init требует --slug")
    mode_of(opt.get("mode") or "interview")       # неверное слово — отказ до архивации прошлого
    questions_of(opt.get("questions") or "one")
    entry_of(opt.get("entry") or "new")
    old = read_state()
    notes = []
    if old and not old.get("finishedAt") and not opt.get("force"):
        die("идёт прогон %s — это продолжение, а не новый прогон (или --force)" % old.get("dir"))
    if old and old.get("dir") and os.path.isdir(os.path.join(A, old["dir"])):
        dst = os.path.join(old["dir"], "state.js")
        if subprocess.run(["git", "-C", A, "mv", "-f", "state.js", dst], capture_output=True).returncode:
            os.replace(STATE, os.path.join(A, dst))
        notes.append("прошлый прогон убран в архив: %s" % dst)
    state = fresh_state(opt)
    log(state, "init")
    os.makedirs(os.path.join(run_dir(state), "rounds"), exist_ok=True)
    notes += install_page(text_opt(opt, "skill-dir"))
    save(state)
    ensure_gitignore()
    register_row(state, "в работе", None)
    notes.append("папка прогона: %s/%s" % (WORK, state["dir"]))
    return state, notes


def cmd_stage(state, pos, opt):
    if not pos:
        die("stage <id> [start|done|skip|fail] [--note …]")
    sid, action = pos[0], (pos[1] if len(pos) > 1 else "start")
    if sid not in ORDER:
        die("этапы: " + ", ".join(ORDER))
    s = stage(state, sid)
    t = now()
    note = text_opt(opt, "note")
    if action == "start":
        s["status"] = "active"
        s.setdefault("startedAt", t)
        s.pop("finishedAt", None)
    elif action == "done":
        s["status"] = "done"
        s.setdefault("startedAt", t)
        s["finishedAt"] = t
    elif action in ("skip", "fail"):
        if not note:
            die("%s требует --note с причиной" % action)
        s["status"] = "skipped" if action == "skip" else "failed"
        s.setdefault("startedAt", t)
        s["finishedAt"] = t
    else:
        die("действие этапа: start | done | skip | fail")
    if note:
        s["note"] = note
    log(state, "stage", id=sid, act=action, note=note if action in ("skip", "fail") else None)


def cmd_set(state, pos):
    for p in pos:
        k, _, v = p.partition("=")
        if not _ or k not in ("title", "mode", "questions", "entry", "result"):
            die("set key=value — можно title, mode, questions, entry, result")
        if k == "mode":
            v = mode_of(v)
        elif k == "questions":
            v = questions_of(v)
        elif k == "entry":
            v = entry_of(v)
        state[k] = None if v in ("", "null") else v
        log(state, "set", key=k)


def cmd_add(state, pos):
    if len(pos) < 2 or pos[0] not in LISTS:
        die("add <%s> \"текст\"" % "|".join(sorted(LISTS)))
    key, vals = pos[0], pos[1:]
    tgt = state.setdefault(key, [])
    fresh = [v for v in vals if v not in tgt]
    tgt.extend(dict.fromkeys(fresh))
    if fresh:
        log(state, "add", key=key, n=len(fresh))


def cmd_ask(state, pos, opt):
    """Прогон ждёт человека: референсы, ответы интервью, выбор превью, решение."""
    kind = pos[0] if pos else ""
    if kind not in WAIT_KINDS:
        die("ask <%s> --note \"что ждём, одной строкой\"" % "|".join(WAIT_KINDS))
    w = state.get("waiting")
    if w and w.get("kind") != kind:
        close_wait(state)
        w = None
    note = text_opt(opt, "note")
    state["waiting"] = {"kind": kind, "since": w["since"] if w else state["updatedAt"], "note": note}
    log(state, "ask", kind=kind, note=note)


def local_ref(state, path):
    """Картинка-референс — копией в папку прогона: сервер отдаёт только .aidesign-work/.
    Возвращает путь от папки прогона или None, если файла нет."""
    src = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.isfile(src):
        return None
    inside = _norm(os.path.abspath(src))
    base = _norm(run_dir(state)) + "/"
    if inside.startswith(base):
        return inside[len(base):]
    os.makedirs(os.path.join(run_dir(state), "refs"), exist_ok=True)
    name = "%02d-%s" % (len(state.get("refs") or []) + 1, os.path.basename(src))
    shutil.copyfile(src, os.path.join(run_dir(state), "refs", name))
    return "refs/" + name


def cmd_ref(state, pos, opt):
    act = pos[0] if pos else ""
    refs = state.setdefault("refs", [])
    notes = []
    if act == "add":
        kind = choice_of(opt.get("kind"), REF_KINDS, "вид референса")
        path = need(opt, "path", "файл, ссылка или текст референса")
        if kind in ("image", "screenshot"):
            copied = local_ref(state, path)
            if copied:
                notes.append("референс скопирован в %s/%s" % (state["dir"], copied))
                path = copied
            else:
                notes.append("! файла %s нет — на панели будет без миниатюры" % path)
        refs.append({"path": path, "kind": kind, "note": text_opt(opt, "note") or "", "at": state["updatedAt"]})
        log(state, "ref", act="add", kind=kind, n=len(refs))
    elif act == "note":
        i = str(opt.get("i") or "")
        if not i.isdigit() or not 1 <= int(i) <= len(refs):
            die("ref note --i N (от 1 до %d) --note \"…\"" % len(refs))
        refs[int(i) - 1]["note"] = need(opt, "note", "что видно в референсе")
        log(state, "ref", act="note", n=int(i))
    else:
        die("ref add --path P --kind %s --note \"…\" | ref note --i N --note \"…\"" % "|".join(REF_KINDS))
    return notes


def cmd_theme(state, pos, opt):
    act = pos[0] if pos else ""
    themes = state.setdefault("themes", [])
    tid = need(opt, "id", "короткий id темы, например tone")
    hit = next((t for t in themes if t.get("id") == tid), None)
    if act == "add":
        title = need(opt, "title", "название темы словами человека")
        if hit:
            hit["title"] = title
        else:
            themes.append({"id": tid, "title": title, "status": "wait"})
        log(state, "theme", act="add", title=title)
    elif act == "set":
        if not hit:
            die("темы %s нет — сначала theme add --id %s --title \"…\"" % (tid, tid))
        hit["status"] = choice_of(opt.get("status"), THEME_STATUSES, "статус темы")
        log(state, "theme", act="set", title=hit["title"], status=hit["status"])
    else:
        die("theme add --id ID --title \"…\" | theme set --id ID --status %s" % "|".join(THEME_STATUSES))


def current_round(state):
    rounds = state.get("rounds") or []
    if not rounds:
        die("кругов ещё нет — начни с `ad.py round new`")
    return rounds[-1]


def option_src(state, src):
    """Путь превью — от папки прогона: панель грузит его через сервер как <dir>/<src>."""
    s = src.replace("\\", "/")
    if os.path.isabs(src):
        s = os.path.relpath(src, run_dir(state)).replace("\\", "/")
    for prefix in ("%s/%s/" % (WORK, state["dir"]), "%s/" % state["dir"]):
        if s.startswith(prefix):
            s = s[len(prefix):]
    while s.startswith("./"):
        s = s[2:]
    if s.startswith("../") or "/../" in s or s.startswith("/") or not s:
        die("превью должно лежать в папке прогона %s/%s/ — иначе сервер его не отдаст" % (WORK, state["dir"]))
    return s


def option_shots(state, src, opt, notes):
    """Снимки превью 1280 и 390: из --shot1280/--shot390 или файлы <имя>-1280.png рядом с превью
    (их кладёт shots.py). Панель показывает снимок там, где живое превью в рамку не пускают."""
    found = {}
    stem = os.path.splitext(src)[0]
    for key, w in SHOT_KEYS:
        given = text_opt(opt, key)
        if given:
            path = option_src(state, given)
            if not os.path.isfile(os.path.join(run_dir(state), path)):
                notes.append("! снимка %s/%s нет — на панели будет живое превью и ссылка" % (state["dir"], path))
            found[key] = path
        elif os.path.isfile(os.path.join(run_dir(state), "%s-%d.png" % (stem, w))):
            found[key] = "%s-%d.png" % (stem, w)
    if not found:
        notes.append("снимков %s нет — python3 %s/shots.py %s/%s/%s, затем этот round option ещё раз"
                     % (os.path.basename(src), WORK, WORK, state["dir"], src))
    return found


def new_round(state, refined=None):
    rounds = state.setdefault("rounds", [])
    n = len(rounds) + 1
    r = {"n": n, "startedAt": state["updatedAt"], "options": [], "feedback": None,
         "chosen": None, "refinedFrom": refined}
    rounds.append(r)
    os.makedirs(os.path.join(run_dir(state), "rounds", "%02d" % n), exist_ok=True)
    return r


def cmd_round(state, pos, opt):
    act = pos[0] if pos else ""
    notes = []
    if act == "new":
        r = new_round(state)
        notes.append("круг %d: превью клади в %s/rounds/%02d/" % (r["n"], state["dir"], r["n"]))
        log(state, "round", act="new", n=r["n"])
        return notes
    r = current_round(state)
    if act == "option":
        oid = choice_of(opt.get("id"), OPTION_IDS, "вариант")
        src = option_src(state, need(opt, "src", "rounds/NN/%s.html" % oid))
        if not os.path.isfile(os.path.join(run_dir(state), src)):
            notes.append("! файла %s/%s пока нет — на панели будет пусто, пока его не положат" % (state["dir"], src))
        o = {"id": oid, "title": need(opt, "title", "название варианта"), "src": src,
             "note": text_opt(opt, "note") or ""}
        o.update(option_shots(state, src, opt, notes))
        r["options"] = [x for x in r["options"] if x.get("id") != oid] + [o]
        r["options"].sort(key=lambda x: x["id"])
        log(state, "round", act="option", n=r["n"], id=oid)
    elif act == "feedback":
        r["feedback"] = need(opt, "text", "что сказал человек, его словами")
        log(state, "round", act="feedback", n=r["n"])
    elif act == "choose":
        cid = choice_of(opt.get("id"), OPTION_IDS + ("none",), "выбор")
        need_n = 1 if r.get("refinedFrom") else FULL_ROUND
        if len(r["options"]) < need_n:
            die("в круге %d вариантов %d из %d — выбор делают, когда показаны все. "
                "Добавь недостающие `round option`" % (r["n"], len(r["options"]), need_n))
        if cid != "none" and cid not in {o["id"] for o in r["options"]}:
            die("варианта %s в круге %d нет" % (cid, r["n"]))
        r["chosen"] = cid
        log(state, "round", act="choose", n=r["n"], id=cid)
    elif act == "refine":
        oid = choice_of(opt.get("id"), OPTION_IDS, "вариант")
        if oid not in {o["id"] for o in r["options"]}:
            die("варианта %s в круге %d нет — дорабатывать нечего" % (oid, r["n"]))
        nr = new_round(state, {"round": r["n"], "id": oid})
        notes.append("круг %d — доработка %s из круга %d: %s/rounds/%02d/"
                     % (nr["n"], oid.upper(), r["n"], state["dir"], nr["n"]))
        log(state, "round", act="refine", n=nr["n"], id=oid, src=r["n"])
    else:
        die("round new | option --id a|b|c --title \"…\" --src rounds/NN/a.html [--note …] "
            "[--shot1280 rounds/NN/a-1280.png --shot390 rounds/NN/a-390.png] | "
            "feedback --text \"…\" | choose --id a|b|c|none | refine --id a")
    return notes


def cmd_direction(state, pos, opt):
    if (pos[0] if pos else "") != "set":
        die("direction set --name \"…\" --summary \"…\" --file DESIGN.md")
    state["direction"] = {"name": need(opt, "name", "имя направления"),
                          "summary": need(opt, "summary", "суть одной-двумя фразами"),
                          "file": text_opt(opt, "file") or "DESIGN.md", "at": state["updatedAt"]}
    log(state, "direction", name=state["direction"]["name"])


def count_of(opt, key):
    v = str(opt.get(key) if opt.get(key) is not None else "")
    if not v.isdigit():
        die("check --findings N --fixed N (целые числа)")
    return int(v)


def cmd_check(state, opt):
    f, x = count_of(opt, "findings"), count_of(opt, "fixed")
    state["check"] = {"findings": f, "fixed": x, "at": state["updatedAt"]}
    log(state, "check", findings=f, fixed=x)


def cmd_finish(state, opt):
    t = now()
    notes = []
    for s in state.get("stages") or []:
        if s.get("status") in ("active", "pending") and s.get("id") == "handoff":
            s["status"], s["finishedAt"] = "done", t
            s.setdefault("startedAt", t)
        elif s.get("status") == "active":
            s["status"], s["finishedAt"] = "done", t
        elif s.get("status") == "pending":
            s["status"], s["note"], s["finishedAt"] = "skipped", s.get("note") or "не понадобился", t
    d = state.get("dir") or ""
    if d.endswith("--wip"):
        new = d[: -len("--wip")]
        if os.path.exists(os.path.join(A, new)):
            notes.append("! папка %s уже есть — оставляю %s" % (new, d))
        elif git_mv(d, new):
            state["dir"] = new
            notes.append("папка прогона: %s/%s" % (WORK, new))
        else:
            notes.append("! не смог переименовать %s — оставляю как есть" % d)
    state["finishedAt"] = t
    state["result"] = text_opt(opt, "result")
    register_row(state, "сдан", state["result"])
    log(state, "finish", result=state["result"])
    return notes


def cmd_backup(state, pos, opt):
    """Копия, которую сделал backup.py create: на панель и в отчёт. Сам копий не делает."""
    if (pos[0] if pos else "") != "add":
        die("backup add --id ID --reason \"до\" --bytes N  (после backup.py create)")
    bid = need(opt, "id", "id копии из backup.py create")
    size = str(opt.get("bytes") or "")
    if not size.isdigit():
        die("backup add --bytes N — размер копии в байтах, целым числом")
    items = [b for b in state.setdefault("backups", []) if b.get("id") != bid]
    items.append({"id": bid, "reason": need(opt, "reason", "до | после | перед-откатом | своё"),
                  "bytes": int(size), "at": state["updatedAt"]})
    state["backups"] = items
    log(state, "backup", id=bid, reason=items[-1]["reason"])


def cmd_figma(state, pos, opt):
    if (pos[0] if pos else "") != "set":
        die("figma set --url https://www.figma.com/… --mode free|paid")
    url = need(opt, "url", "ссылка на файл Figma")
    if not re.match(r"^https?://", url):
        die("ссылка Figma — только http(s)://, а не «%s»" % url)
    state["figma"] = {"url": url, "mode": choice_of(opt.get("mode"), FIGMA_MODES, "тариф Figma"),
                      "updatedAt": state["updatedAt"]}
    log(state, "figma", mode=state["figma"]["mode"])


def cmd_toolkit(state, pos, opt):
    if (pos[0] if pos else "") != "set":
        die("toolkit set --missing a,b --installed c --skipped d")
    names = lambda k: [x.strip() for x in (text_opt(opt, k) or "").split(",") if x.strip()]
    state["toolkit"] = {"checkedAt": state["updatedAt"], "missing": names("missing"),
                        "installed": names("installed"), "skipped": names("skipped")}
    log(state, "toolkit", n=len(state["toolkit"]["missing"]))


# ── медиа: бюджет «1б», траты, подключённые генераторы, источник ────────────

def amount_of(v, what):
    """Неотрицательное число: целое остаётся целым (100, а не 100.0)."""
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        x = -1
    if not str(v or "").strip() or x != x or x < 0 or x == float("inf"):
        die("%s — неотрицательное число, а не «%s»" % (what, v))
    return int(x) if x == int(x) else round(x, 4)


def media_of(state):
    m = state.get("media")
    if not isinstance(m, dict):
        m = state["media"] = fresh_media()
    for k, v in fresh_media().items():
        m.setdefault(k, v)
    return m


def media_spent(m):
    """Сколько потрачено. Правило одно для ad.py, rules.py («Сейчас») и панели (mediaSums): в сумму идут
    траты в единице бюджета и старые записи без единицы. Чужую единицу spend и budget не принимают."""
    unit = (m.get("budget") or {}).get("unit")
    total = sum(x.get("amount") or 0 for x in m.get("spent") or []
                if not unit or not x.get("unit") or x.get("unit") == unit)
    return int(total) if total == int(total) else round(total, 4)


def media_units(m):
    """Единицы, в которых уже записаны траты (у старых записей без единицы — пусто, не считается)."""
    return {x.get("unit") for x in m.get("spent") or [] if x.get("unit")}


def media_check(state, opt):
    """Хватит ли бюджета на следующую платную генерацию. Состояние не меняет: только код и строка."""
    m = media_of(state)
    amount = amount_of(opt.get("amount"), "media check --amount")
    b = m.get("budget")
    asked = text_opt(opt, "unit")
    if b and asked and asked != b["unit"]:
        print("бюджет в %s, а цена в %s — сравнить нельзя: спроси человека, как пересчитать" % (b["unit"], asked))
        return 1
    if not b:
        print("бюджета на медиа нет — платная генерация только после вопроса человеку о сумме "
              "(ad.py media budget --limit N --unit …)")
        return 1
    spent = media_spent(m)
    left = b["limit"] - spent
    if amount > left + 1e-9:
        print("выйдет за бюджет: потрачено %s из %s %s, осталось %s, нужно %s — спроси человека"
              % (spent, b["limit"], b["unit"], round(left, 4), amount))
        return 1
    print("в бюджете: потрачено %s из %s %s, после этой — %s" % (spent, b["limit"], b["unit"], round(spent + amount, 4)))
    return 0


def media_catalog(state):
    """Каталог генераторов: копия рядом с ad.py (её кладёт init), иначе из папки навыка."""
    for path in (os.path.join(A, os.path.basename(MEDIA_CATALOG)),
                 os.path.join(state.get("skillDir") or "", MEDIA_CATALOG)):
        try:
            with open(path, encoding="utf-8") as f:
                return {s["id"]: s for s in json.load(f).get("services") or [] if isinstance(s, dict) and s.get("id")}
        except (OSError, ValueError, KeyError, AttributeError):
            continue
    return {}


def cmd_media(state, pos, opt):
    act, notes = (pos[0] if pos else ""), []
    m = media_of(state)
    if act == "budget":
        unit = need(opt, "unit", "кредитов | ₽ | $ — в чём считает сервис")
        other = media_units(m) - {unit}
        if other:
            die("траты уже записаны в %s, а бюджет — в %s: единицу при записанных тратах не меняем, спроси "
                "человека, как пересчитать (поднять лимит в той же единице можно)" % (", ".join(sorted(other)), unit))
        m["budget"] = {"limit": amount_of(opt.get("limit"), "media budget --limit"), "unit": unit, "at": state["updatedAt"]}
        log(state, "media", act="budget", limit=m["budget"]["limit"], unit=unit)
    elif act == "spend":
        b = m.get("budget") or {}
        x = {"service": need(opt, "service", "id сервиса, например higgsfield"),
             "amount": amount_of(opt.get("amount"), "media spend --amount"),
             "unit": text_opt(opt, "unit") or b.get("unit") or "", "item": need(opt, "item", "что сгенерировано"),
             "at": state["updatedAt"]}
        if b and x["unit"] != b["unit"]:
            die("в бюджете %s, а трата в %s — спроси человека, как пересчитать, и запиши в %s"
                % (b["unit"], x["unit"], b["unit"]))
        if not b and not x["unit"]:
            die("бюджета нет — у траты нужна единица: --unit кредитов | ₽ | $")
        if not b and media_units(m) - {x["unit"]}:
            die("траты уже записаны в %s, а эта — в %s: спроси человека, как пересчитать"
                % (", ".join(sorted(media_units(m))), x["unit"]))
        m["spent"].append(x)
        if not b:
            notes.append("! трата без бюджета — спроси человека о сумме: ad.py media budget --limit N --unit …")
        elif media_spent(m) > b["limit"]:
            notes.append("! бюджет превышен: потрачено %s из %s %s — следующая платная генерация только с "
                         "разрешения человека" % (media_spent(m), b["limit"], b["unit"]))
        log(state, "media", act="spend", service=x["service"], amount=x["amount"], unit=x["unit"])
    elif act == "connected":
        cat = media_catalog(state)
        ids = [x.strip() for x in (text_opt(opt, "ids") or "").split(",") if x.strip()]
        m["connected"] = [{"id": i, "title": (cat.get(i) or {}).get("title") or i,
                           "kinds": list((cat.get(i) or {}).get("kinds") or [])} for i in dict.fromkeys(ids)]
        log(state, "media", act="connected", n=len(m["connected"]))
    elif act == "sources":
        m["sources"] = choice_of(opt.get("set"), MEDIA_SOURCES, "источник медиа")
        log(state, "media", act="sources", set=m["sources"])
    elif act == "recorded":                      # зовёт media.py record: опись assets/media.json изменилась
        log(state, "media", act="recorded", slot=need(opt, "slot", "место в описи, например hero"))
    else:
        die("media budget --limit N --unit U | spend --service S --amount A --item \"…\" | check --amount A | "
            "connected --ids a,b | sources --set %s | recorded --slot S" % "|".join(MEDIA_SOURCES))
    return notes


# События, которые меняют проект: после них «Сейчас» в блоке aidesign переписывается сам.
RULE_STAGES = {"build": "сборка готова", "check": "проверка пройдена", "handoff": "передача готова"}


def rules_event(state, cmd, pos):
    """Слова события для строки «Обновлено» или None, если проект не менялся."""
    if cmd == "stage":
        return RULE_STAGES.get(pos[0]) if len(pos) > 1 and pos[1] == "done" else None
    if cmd == "direction":
        return "направление «%s» выбрано" % (state.get("direction") or {}).get("name", "")
    if cmd == "backup":
        b = (state.get("backups") or [{}])[-1]
        return "копия «%s» — %s" % (b.get("reason"), b.get("id"))
    if cmd == "figma":
        return "Figma подключена или обновлена"
    if cmd == "media" and pos and pos[0] in ("budget", "spend", "sources", "recorded"):
        return {"budget": "бюджет медиа назван", "spend": "трата на медиа записана",
                "sources": "источник медиа выбран", "recorded": "опись медиа обновлена"}[pos[0]]
    return {"toolkit": "оснащение проверено", "finish": "прогон сдан"}.get(cmd)


def sync_rules(state, event):
    """Блок aidesign в AGENTS.md / CLAUDE.md — через rules.py рядом с ad.py (его кладёт init).
    Сбой правил не роняет учёт прогона: строка «!» и дальше.
    Готовый сайт: файлы человека не меняются до первой копии «до» (бэкап — перед первой правкой)."""
    if state.get("entry") == "existing" and not state.get("backups"):
        return ["правила проекта (блок aidesign) — после первой копии проекта: на готовом сайте сначала бэкап"]
    path = os.path.join(A, "rules.py")
    if not os.path.isfile(path):
        return ["! rules.py нет рядом с ad.py — правила проекта не обновлены: init --skill-dir перекопирует инструменты"]
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("aidesign_rules", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.update(ROOT, state, event, WORK)
    except (OSError, ValueError, AttributeError, SyntaxError) as e:
        return ["! правила проекта не обновлены: %s" % e]


HANDLERS = {
    "backup": lambda s, p, o: cmd_backup(s, p, o),
    "figma": lambda s, p, o: cmd_figma(s, p, o),
    "toolkit": lambda s, p, o: cmd_toolkit(s, p, o),
    "media": lambda s, p, o: cmd_media(s, p, o),
    "ref": lambda s, p, o: cmd_ref(s, p, o),
    "theme": lambda s, p, o: cmd_theme(s, p, o),
    "round": lambda s, p, o: cmd_round(s, p, o),
    "direction": lambda s, p, o: cmd_direction(s, p, o),
    "check": lambda s, p, o: cmd_check(s, o),
    "stage": lambda s, p, o: cmd_stage(s, p, o),
    "set": lambda s, p, o: cmd_set(s, p),
    "add": lambda s, p, o: cmd_add(s, p),
    "ask": lambda s, p, o: cmd_ask(s, p, o),
    "answered": lambda s, p, o: close_wait(s),
    "finish": lambda s, p, o: cmd_finish(s, o),
}


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["--serve-http"]:
        sys.exit(serve_http_cli(argv[1:]))
    if "--stop-now" in argv:
        i = argv.index("--stop-now")
        stop_now(argv[i + 1] if i + 1 < len(argv) else None)
        return
    pos, opt = parse_args(argv)
    cmd = pos[0] if pos else ""
    notes = []
    if cmd == "init":
        state, notes = cmd_init(opt)
    else:
        state = read_state()
        if state is None:
            die("state.js ещё нет — начни с `ad.py init`")
        if cmd not in ("", "sync") and cmd not in HANDLERS:
            die("неизвестная команда %s — список в начале ad.py" % cmd)
        if pos[:2] == ["media", "check"]:                  # вопрос, а не событие: без записи и сервера
            sys.exit(media_check(state, opt))
        if cmd not in ("", "sync"):
            # Время события ставится до команды: ей самой и ленте нужна одна метка.
            state["updatedAt"] = now()
            beat(state)
        if cmd in MOVES_ON:
            close_wait(state)
        if cmd in HANDLERS:
            notes = HANDLERS[cmd](state, pos[1:], opt) or []
            event = rules_event(state, cmd, pos[1:])
            if event:
                notes += sync_rules(state, event)
    notes = close_passed(state) + notes
    save(state)
    snap = write_snapshot(state)
    if opt.get("stop"):
        srv = stop_explicit()
    elif cmd == "finish":
        srv = stop_later()
    elif opt.get("no-serve"):
        srv = "сервер не проверялся"
    else:
        srv = serve(state)
    rounds = state.get("rounds") or []
    print("%s · %s · кругов превью: %d" % (snap, srv, len(rounds)))
    for line in notes:
        print("  " + (line if line.startswith("!") else "· " + line))
    for line in audit(state)[:5]:
        print("  ! " + line)
    if opt.get("check-update"):
        note = check_update(state)
        if note:
            print("  ↑ " + note)


if __name__ == "__main__":
    main()
