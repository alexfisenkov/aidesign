"""Тесты skills/aidesign/tools/ad.py — учёта прогона AI Design и панели.

Запуск из корня репозитория:  python3 -B -m unittest discover -s tests
Каждый тест заводит временный проект, кладёт в .aidesign-work/ копию ad.py
и зовёт её отдельным процессом — как агент. Сервер поднимает только класс Server.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILL = os.path.join(REPO, "skills", "aidesign")
AD = os.path.join(SKILL, "tools", "ad.py")
TEMPLATE = os.path.join(SKILL, "phases", "dashboard-template.html")

STATE_KEYS = {"version", "slug", "dir", "title", "mode", "questions", "entry", "skillDir", "skillVersion",
              "startedAt", "updatedAt", "finishedAt", "stages", "waiting", "waits", "beats", "log",
              "refs", "themes", "rounds", "direction", "check", "report", "assumptions", "result", "rev",
              "backups", "figma", "toolkit"}
NEW_TOOLS = ("setup.py", "backup.py", "scaffold.py", "designsystem.py")
STAGES = ["preflight", "refs", "interview", "previews", "build", "check", "handoff"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Project(unittest.TestCase):
    """Временный проект и поддельная папка навыка: шаблон панели настоящий,
    SKILL.md с версией и examples/ — свои, чтобы не зависеть от других задач."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ad-test-")
        self.skill = os.path.join(self.root, "_skill")
        write(os.path.join(self.skill, "SKILL.md"), "---\nname: aidesign\nmetadata:\n  version: 0.1.0\n---\n# AI Design\n")
        os.makedirs(os.path.join(self.skill, "phases"))
        shutil.copy(TEMPLATE, os.path.join(self.skill, "phases", "dashboard-template.html"))
        write(os.path.join(self.skill, "examples", "INDEX.json"),
              json.dumps([{"id": "demo", "title": "Демо", "style": "редакционный",
                           "techniques": ["прокрутка"], "file": "demo/index.html"}], ensure_ascii=False))
        write(os.path.join(self.skill, "examples", "demo", "index.html"), "<!doctype html><title>demo</title>")
        self.a = os.path.join(self.root, ".aidesign-work")
        os.makedirs(self.a)
        shutil.copy(AD, os.path.join(self.a, "ad.py"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def ad(self, *args, serve=False):
        env = dict(os.environ, AIDESIGN_NO_UPDATE_CHECK="1")
        env.pop("CI", None)
        env.pop("SSH_CONNECTION", None)
        tail = [] if serve else ["--no-serve"]
        r = subprocess.run([sys.executable, "-B", os.path.join(self.a, "ad.py")] + list(args) + tail,
                           capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.root, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def ok(self, *args):
        code, out = self.ad(*args)
        self.assertEqual(code, 0, out)
        return out

    def fails(self, *args):
        code, out = self.ad(*args)
        self.assertNotEqual(code, 0, out)
        return out

    def state(self):
        return json.loads(read(os.path.join(self.a, "state.js")).split("=", 1)[1])

    def stage(self, sid):
        return next(s for s in self.state()["stages"] if s["id"] == sid)

    def init(self, *extra):
        out = self.ok("init", "--slug", "studio", "--title", "Студия", "--entry", "new",
                      "--skill-dir", self.skill, *extra)
        self.dir = os.path.join(self.a, self.state()["dir"])
        return out

    def preview(self, n, oid):
        rel = "rounds/%02d/%s.html" % (n, oid)
        write(os.path.join(self.dir, rel), "<!doctype html><title>%s</title>" % oid)
        return rel


class Init(Project):
    def test_init_creates_run_with_exact_fields(self):
        self.init()
        s = self.state()
        self.assertEqual(set(s), STATE_KEYS)
        self.assertEqual(s["version"], 1)
        self.assertRegex(s["dir"], r"^\d{4}-\d{2}-\d{2}-studio--wip$")
        self.assertEqual([x["id"] for x in s["stages"]], STAGES)
        self.assertEqual([x["status"] for x in s["stages"]], ["active"] + ["pending"] * 6)
        self.assertRegex(s["startedAt"], r"T\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        self.assertEqual((s["mode"], s["questions"], s["entry"]), ("interview", "one", "new"))
        self.assertEqual(s["skillVersion"], "0.1.0")
        self.assertTrue(os.path.isdir(os.path.join(self.dir, "rounds")))
        self.assertEqual((s["backups"], s["figma"], s["toolkit"]), ([], None, None))

    def test_init_copies_the_new_tools(self):
        for name in NEW_TOOLS + ("check.py",):
            write(os.path.join(self.skill, "tools", name), "# %s\n" % name)
        out = self.init()
        for name in NEW_TOOLS + ("check.py",):
            self.assertEqual(read(os.path.join(self.a, name)), "# %s\n" % name, out)

    def test_init_installs_panel_examples_registry_and_gitignore(self):
        self.init()
        page = read(os.path.join(self.a, "dashboard.html"))
        self.assertIn("window.STATE={", page)
        self.assertTrue(os.path.exists(os.path.join(self.a, "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(self.a, "examples", "INDEX.json")))
        self.assertIn("в работе", read(os.path.join(self.a, "README.md")))
        self.assertIn(".aidesign-work/serve.*", read(os.path.join(self.root, ".gitignore")))

    def test_init_takes_modes_entries_and_question_forms(self):
        self.init("--mode", "auto", "--questions", "rounds")
        self.assertEqual(self.state()["mode"], "auto")
        self.assertEqual(self.state()["questions"], "rounds")
        self.ok("init", "--slug", "x", "--force", "--mode", "important", "--entry", "existing")
        self.assertEqual((self.state()["mode"], self.state()["entry"]), ("important", "existing"))

    def test_init_refuses_unknown_words_and_a_live_run(self):
        self.assertIn("auto", self.fails("init", "--slug", "x", "--mode", "turbo"))
        self.assertIn("existing", self.fails("init", "--slug", "x", "--entry", "old"))
        self.init()
        self.assertIn("продолжение", self.fails("init", "--slug", "other"))

    def test_init_archives_finished_run(self):
        self.init()
        first = self.state()["dir"]
        self.ok("finish", "--result", "готово")
        self.ok("init", "--slug", "second")
        self.assertTrue(os.path.isfile(os.path.join(self.a, first.replace("--wip", ""), "state.js")))
        self.assertTrue(self.state()["dir"].endswith("second--wip"))

    def test_commands_need_a_run(self):
        self.assertIn("init", self.fails("stage", "refs"))


class Stages(Project):
    def test_next_stage_closes_previous(self):
        self.init()
        self.ok("stage", "refs")
        self.ok("stage", "interview")
        self.assertEqual(self.stage("refs")["status"], "done")
        self.assertEqual(self.stage("interview")["status"], "active")
        self.assertEqual(self.stage("preflight")["status"], "done")

    def test_skip_needs_a_reason_and_unknown_stage_is_refused(self):
        self.init()
        self.assertIn("--note", self.fails("stage", "interview", "skip"))
        self.ok("stage", "interview", "skip", "--note", "референсов хватило")
        self.assertEqual(self.stage("interview")["status"], "skipped")
        self.assertIn("previews", self.fails("stage", "spec"))

    def test_finish_freezes_the_run(self):
        self.init()
        self.ok("stage", "build")
        self.ok("finish", "--result", "Лендинг собран")
        s = self.state()
        self.assertIsNotNone(s["finishedAt"])
        self.assertEqual(s["result"], "Лендинг собран")
        self.assertFalse(s["dir"].endswith("--wip"))
        self.assertTrue(os.path.isdir(os.path.join(self.a, s["dir"])))
        self.assertEqual(self.stage("handoff")["status"], "done")
        self.assertIn("сдан", read(os.path.join(self.a, "README.md")))

    def test_set_changes_only_allowed_fields(self):
        self.init()
        self.ok("set", "questions=rounds", "mode=auto")
        self.assertEqual((self.state()["questions"], self.state()["mode"]), ("rounds", "auto"))
        self.fails("set", "stages=x")
        self.fails("set", "mode=manual")


class Waiting(Project):
    def test_ask_and_answered_record_the_pause(self):
        self.init()
        self.ok("ask", "refs", "--note", "пришли картинки")
        w = self.state()["waiting"]
        self.assertEqual((w["kind"], w["note"]), ("refs", "пришли картинки"))
        self.ok("answered")
        s = self.state()
        self.assertIsNone(s["waiting"])
        self.assertEqual(len(s["waits"]), 1)
        self.assertEqual(s["waits"][0]["from"], w["since"])

    def test_moving_on_closes_a_forgotten_wait(self):
        self.init()
        self.ok("ask", "previews", "--note", "выбери превью")
        self.ok("round", "new")
        self.assertIsNone(self.state()["waiting"])
        self.assertEqual(self.state()["waits"][0]["kind"], "previews")

    def test_unknown_wait_kind_is_refused(self):
        self.init()
        self.assertIn("previews", self.fails("ask", "briefing"))


class Rounds(Project):
    def three(self):
        for oid in "abc":
            self.ok("round", "option", "--id", oid, "--title", "Вариант " + oid, "--src", self.preview(1, oid))

    def test_round_new_opens_numbered_round_and_folder(self):
        self.init()
        self.ok("round", "new")
        r = self.state()["rounds"]
        self.assertEqual([x["n"] for x in r], [1])
        self.assertEqual(r[0]["options"], [])
        self.assertTrue(os.path.isdir(os.path.join(self.dir, "rounds", "01")))

    def test_option_needs_a_round_and_stays_inside_the_run(self):
        self.init()
        self.assertIn("round new", self.fails("round", "option", "--id", "a", "--title", "A", "--src", "rounds/01/a.html"))
        self.ok("round", "new")
        self.fails("round", "option", "--id", "a", "--title", "A", "--src", "../../etc/passwd")
        self.fails("round", "option", "--id", "d", "--title", "D", "--src", "rounds/01/d.html")
        self.ok("round", "option", "--id", "a", "--title", "A", "--src", self.preview(1, "a"), "--note", "строгий")
        o = self.state()["rounds"][0]["options"][0]
        self.assertEqual(o, {"id": "a", "title": "A", "src": "rounds/01/a.html", "note": "строгий"})

    def test_choose_needs_all_three_options(self):
        self.init()
        self.ok("round", "new")
        self.ok("round", "option", "--id", "a", "--title", "A", "--src", self.preview(1, "a"))
        out = self.fails("round", "choose", "--id", "a")
        self.assertIn("1 из 3", out)
        self.assertIsNone(self.state()["rounds"][0]["chosen"])
        self.ok("round", "option", "--id", "b", "--title", "B", "--src", self.preview(1, "b"))
        self.ok("round", "option", "--id", "c", "--title", "C", "--src", self.preview(1, "c"))
        self.ok("round", "choose", "--id", "b")
        self.assertEqual(self.state()["rounds"][0]["chosen"], "b")

    def test_history_keeps_feedback_and_choices(self):
        self.init()
        self.ok("round", "new")
        self.three()
        self.ok("round", "feedback", "--text", "в A шрифт, в C цвет")
        self.ok("round", "choose", "--id", "none")
        self.ok("round", "new")
        r = self.state()["rounds"]
        self.assertEqual([x["n"] for x in r], [1, 2])
        self.assertEqual((r[0]["feedback"], r[0]["chosen"]), ("в A шрифт, в C цвет", "none"))
        self.assertIsNone(r[1]["chosen"])

    def test_refine_opens_a_round_from_one_option(self):
        self.init()
        self.ok("round", "new")
        self.three()
        self.fails("round", "refine", "--id", "d")
        self.ok("round", "refine", "--id", "a")
        r = self.state()["rounds"]
        self.assertEqual(r[1]["n"], 2)
        self.assertEqual(r[1]["refinedFrom"], {"round": 1, "id": "a"})
        self.ok("round", "option", "--id", "a", "--title", "A2", "--src", self.preview(2, "a"))
        self.ok("round", "choose", "--id", "a")
        self.assertEqual(self.state()["rounds"][1]["chosen"], "a")

    def test_choose_refuses_an_option_that_is_not_there(self):
        self.init()
        self.ok("round", "new")
        self.three()
        self.fails("round", "choose", "--id", "x")


class Records(Project):
    def test_refs_are_added_copied_and_described(self):
        self.init()
        write(os.path.join(self.root, "референсы", "1.png"), "png")
        self.ok("ref", "add", "--path", "референсы/1.png", "--kind", "image", "--note", "беж")
        self.ok("ref", "add", "--path", "https://example.com", "--kind", "url", "--note", "сетка")
        self.ok("ref", "note", "--i", "2", "--note", "сетка и шрифт")
        refs = self.state()["refs"]
        self.assertEqual([r["kind"] for r in refs], ["image", "url"])
        self.assertEqual(set(refs[0]), {"path", "kind", "note", "at"})
        self.assertTrue(os.path.isfile(os.path.join(self.dir, refs[0]["path"])))
        self.assertEqual(refs[1]["note"], "сетка и шрифт")
        self.fails("ref", "add", "--path", "x", "--kind", "video")
        self.fails("ref", "note", "--i", "9", "--note", "нет такого")

    def test_themes_move_through_statuses(self):
        self.init()
        self.ok("theme", "add", "--id", "tone", "--title", "Тон")
        self.ok("theme", "set", "--id", "tone", "--status", "decided")
        self.assertEqual(self.state()["themes"], [{"id": "tone", "title": "Тон", "status": "decided"}])
        self.fails("theme", "set", "--id", "tone", "--status", "maybe")
        self.fails("theme", "set", "--id", "color", "--status", "asked")

    def test_direction_check_and_lists(self):
        self.init()
        self.ok("direction", "set", "--name", "Тёплая редакция", "--summary", "крупный антиква", "--file", "DESIGN.md")
        self.ok("check", "--findings", "7", "--fixed", "6")
        self.ok("add", "report", "Один контраст оставлен")
        self.ok("add", "assumptions", "Шрифт выбран за тебя")
        s = self.state()
        self.assertEqual({k: s["direction"][k] for k in ("name", "summary", "file")},
                         {"name": "Тёплая редакция", "summary": "крупный антиква", "file": "DESIGN.md"})
        self.assertEqual((s["check"]["findings"], s["check"]["fixed"]), (7, 6))
        self.assertEqual((s["report"], s["assumptions"]), (["Один контраст оставлен"], ["Шрифт выбран за тебя"]))
        self.fails("check", "--findings", "много", "--fixed", "1")

    def test_backup_figma_and_toolkit_fields(self):
        self.init()
        self.ok("backup", "add", "--id", "20261119-101500-до", "--reason", "до", "--bytes", "2048")
        self.ok("backup", "add", "--id", "20261119-120000-после", "--reason", "после", "--bytes", "4096")
        b = self.state()["backups"]
        self.assertEqual([(x["id"], x["reason"], x["bytes"]) for x in b],
                         [("20261119-101500-до", "до", 2048), ("20261119-120000-после", "после", 4096)])
        self.assertTrue(all(x["at"] for x in b))
        self.fails("backup", "add", "--id", "x", "--reason", "до", "--bytes", "много")
        self.ok("figma", "set", "--url", "https://www.figma.com/design/abc/Site", "--mode", "free")
        f = self.state()["figma"]
        self.assertEqual((f["url"], f["mode"]), ("https://www.figma.com/design/abc/Site", "free"))
        self.assertTrue(f["updatedAt"])
        self.fails("figma", "set", "--url", "javascript:alert(1)", "--mode", "free")
        self.fails("figma", "set", "--url", "https://www.figma.com/x", "--mode", "pro")
        self.ok("toolkit", "set", "--missing", "ffmpeg", "--installed", "node,playwright", "--skipped", "figma")
        t = self.state()["toolkit"]
        self.assertEqual((t["missing"], t["installed"], t["skipped"]), (["ffmpeg"], ["node", "playwright"], ["figma"]))
        self.assertTrue(t["checkedAt"])
        kinds = [e["k"] for e in self.state()["log"]]
        self.assertTrue({"backup", "figma", "toolkit"} <= set(kinds))

    def test_value_starting_with_dashes_goes_through_equals(self):
        self.init()
        self.ok("ask", "refs", "--note=--срочно: пришли картинки")
        self.assertEqual(self.state()["waiting"]["note"], "--срочно: пришли картинки")
        self.ok("round", "new")
        self.ok("round", "feedback", "--text=--меньше шума, больше воздуха")
        self.assertEqual(self.state()["rounds"][0]["feedback"], "--меньше шума, больше воздуха")

    def test_every_event_beats_and_logs(self):
        self.init()
        before = len(self.state()["log"])
        self.ok("theme", "add", "--id", "tone", "--title", "Тон")
        s = self.state()
        self.assertEqual(len(s["log"]), before + 1)
        self.assertIn(s["updatedAt"], s["beats"])


@unittest.skipUnless(shutil.which("node"), "node не установлен")
class PanelClock(unittest.TestCase):
    """Часы панели: функции времени из шаблона, как есть, в node."""

    def active(self, state, start, end):
        page = read(TEMPLATE)
        code = page[page.index("/*TIME-BEGIN*/"):page.index("/*TIME-END*/")]
        js = code + "\nconst S=%s;MARKS=collectMarks(S);WAITS=collectWaits(S);" \
                    "console.log(activeMs(%s,%s));" % (json.dumps(state), json.dumps(start), json.dumps(end))
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return int(r.stdout.strip().splitlines()[-1])

    def test_wait_is_not_working_time_and_clock_stops_on_finish(self):
        t = lambda m: "2026-11-18T10:%02d:00+03:00" % m
        state = {"startedAt": t(0), "updatedAt": t(30), "finishedAt": t(30),
                 "beats": [t(0), t(5), t(10), t(20), t(25), t(30)],
                 "waits": [{"kind": "interview", "from": t(10), "to": t(20)}], "stages": []}
        self.assertEqual(self.active(state, t(0), t(30)), 20 * 60000)


class Template(unittest.TestCase):
    def test_panel_has_snapshot_markers_stages_and_file_hint(self):
        page = read(TEMPLATE)
        self.assertIn("/*STATE-BEGIN*/window.STATE=null;/*STATE-END*/", page)
        self.assertIn("const STAGE_IDS = %s;" % json.dumps(STAGES).replace('"', "'").replace(", ", ","), page)
        self.assertIn("http://localhost", page)
        self.assertIn("examples/INDEX.json", page)
        # Остатки форка (ключи хранилища, папка AISpa) и имя базы — только в LICENSE и README.
        self.assertNotRegex(page.lower(), "auto" + "pilot|nick" + r" vels|aispa-|\.aispa-work|>aispa<")

    @unittest.skipUnless(shutil.which("node"), "node не установлен")
    def test_panel_script_parses(self):
        page = read(TEMPLATE)
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        tmp = tempfile.mkdtemp(prefix="ad-js-")
        try:
            for i, body in enumerate(scripts):
                path = os.path.join(tmp, "s%d.js" % i)
                write(path, body)
                r = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def node_eval(names, expr):
    """Однострочные чистые функции шаблона — в node, результат через JSON."""
    page = read(TEMPLATE)
    code = []
    for name in names:
        m = re.search(r"^const %s = .*$" % name, page, re.M)
        assert m, "нет функции %s" % name
        code.append(m.group(0))
    r = subprocess.run(["node", "-e", "\n".join(code) + "\nconsole.log(JSON.stringify(%s));" % expr],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class PanelIsolation(unittest.TestCase):
    """Превью — чужая страница: она не должна читать панель (без allow-same-origin)."""

    def test_preview_iframes_have_no_same_origin(self):
        page = read(TEMPLATE)
        sandboxes = re.findall(r"<iframe[^>]*sandbox=\"([^\"]*)\"", page)
        self.assertGreaterEqual(len(sandboxes), 2)
        for s in sandboxes:
            self.assertIn("allow-scripts", s)
            self.assertNotIn("allow-same-origin", s)
        self.assertNotRegex(page, r"<iframe(?![^>]*sandbox=)[^>]*>")


class LightboxLoading(unittest.TestCase):
    """Окно увеличения не пустое: пока грузится — строка, сервер погас или файла нет — что делать."""

    def test_lightbox_says_loading_and_failure_instead_of_a_blank_frame(self):
        page = read(TEMPLATE)
        show = page[page.index("function lbShow()"):page.index("function lbFit()")]
        self.assertIn("lb-wait", show)
        self.assertIn("lbWatch(", show)
        self.assertIn("method: 'HEAD'", show)
        for key in ("lbLoading:", "lbMissing:", "lbDown:"):
            self.assertEqual(page.count(key), 2, key)                     # ru и en
        self.assertIn(".lb-box.loaded iframe{opacity:1}", page)


class PanelNewBlocks(unittest.TestCase):
    """Блоки итерации 19.11: бэкапы с командой отката, Figma, строка оснащения."""

    def test_template_reads_the_new_fields(self):
        page = read(TEMPLATE)
        for field in ("S.backups", "S.figma", "S.toolkit"):
            self.assertIn(field, page)
        self.assertIn("httpHref(S.figma.url)", page)

    @unittest.skipUnless(shutil.which("node"), "node не установлен")
    def test_restore_command_and_toolkit_line(self):
        self.assertEqual(node_eval(["restoreCmd"], "restoreCmd('20261119-101500-до')"),
                         "python3 .aidesign-work/backup.py restore --id 20261119-101500-до --yes")
        got = node_eval(["toolkitParts"], "[toolkitParts({missing:['ffmpeg'],installed:['node'],skipped:[]}),"
                                          "toolkitParts(null), toolkitParts({missing:[],installed:[],skipped:['figma']})]")
        self.assertEqual(got, [{"missing": ["ffmpeg"], "installed": ["node"], "skipped": []}, None,
                               {"missing": [], "installed": [], "skipped": ["figma"]}])


class Themes(unittest.TestCase):
    """Счётчик «решено N из M»: ответ и решение — обе закрытые темы."""

    @unittest.skipUnless(shutil.which("node"), "node не установлен")
    def test_answered_and_decided_both_count_as_done(self):
        page = read(TEMPLATE)
        m = re.search(r"^const themeDone = .*$", page, re.M)
        self.assertIsNotNone(m, "нет функции themeDone")
        themes = [{"status": s} for s in ("wait", "asked", "answered", "decided", "decided")]
        script = m.group(0) + "\nconsole.log(%s.filter(themeDone).length);" % json.dumps(themes)
        r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "3")

    def test_counter_uses_the_shared_rule(self):
        page = read(TEMPLATE)
        self.assertIn("themes.filter(themeDone).length", page)


class Origin(unittest.TestCase):
    """Шапки происхождения форка: основа названа, имени её основы нет."""

    def test_ad_py_names_its_base(self):
        head = "\n".join(read(AD).splitlines()[:5])
        self.assertIn("основано на AISpa 1.0.2 (MIT)", head)

    def test_panel_names_its_base_in_the_first_lines(self):
        head = "\n".join(read(TEMPLATE).splitlines()[:3])
        self.assertRegex(head, r"<!-- [^>]*основано на AISpa 1\.0\.2 \(MIT\)")


class RefLinks(unittest.TestCase):
    """Ссылка-референс: в href попадают только http: и https:, остальное — текстом."""

    def test_every_dynamic_href_goes_through_the_http_filter(self):
        page = read(TEMPLATE)
        dynamic = re.findall(r'href="\$\{([^}]*)\}"', page)
        self.assertTrue(dynamic)
        for expr in dynamic:
            self.assertRegex(expr, r"^esc\(httpHref\(", expr)

    @unittest.skipUnless(shutil.which("node"), "node не установлен")
    def test_http_filter_lets_through_only_http_and_https(self):
        page = read(TEMPLATE)
        m = re.search(r"^const httpHref = .*$", page, re.M)
        self.assertIsNotNone(m, "нет функции httpHref")
        cases = ["https://example.com/a?b=1", "http://example.com", "HTTPS://Example.com",
                 "javascript:alert(1)", " javascript:alert(1)", "data:text/html,x", "file:///etc/passwd",
                 "//evil.example", "refs/1.png", "", None]
        script = m.group(0) + "\nconsole.log(JSON.stringify(%s.map(httpHref)));" % json.dumps(cases)
        r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual(got[0], "https://example.com/a?b=1")
        self.assertEqual(got[1], "http://example.com/")
        self.assertEqual(got[2], "https://example.com/")
        self.assertEqual(got[3:], [""] * (len(cases) - 3))


class Server(Project):
    """Сервер поднимается при init и заново — голым вызовом ad.py, на том же порту."""

    def get(self, port, path):
        with urllib.request.urlopen("http://127.0.0.1:%d/%s" % (port, path), timeout=3) as r:
            return r.status, r.read().decode("utf-8", "replace")

    def pid(self):
        port, pid = read(os.path.join(self.a, "serve.pid")).split()
        return int(port), int(pid)

    def tearDown(self):
        # До удаления папки: cleanup-функции идут после tearDown, когда serve.pid уже нет.
        ps = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
        for line in ps.splitlines():
            pid, _, cmd = line.strip().partition(" ")
            if "http.server" in cmd and self.a in cmd and pid.isdigit():
                try:
                    os.kill(int(pid), 15)
                except OSError:
                    pass
        super().tearDown()

    def test_server_serves_panel_and_previews_and_comes_back(self):
        self.init()
        code, out = self.ad(serve=True)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"http://localhost:\d+/dashboard\.html")
        port, pid = self.pid()
        self.ok("round", "new")
        self.preview(1, "a")
        status, body = self.get(port, "%s/rounds/01/a.html" % self.state()["dir"])
        self.assertEqual((status, body.count("<title>a</title>")), (200, 1))
        self.assertEqual(self.get(port, "examples/INDEX.json")[0], 200)
        os.kill(pid, 15)
        time.sleep(0.5)
        code, out = self.ad(serve=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.pid()[0], port)
        self.assertEqual(self.get(port, "dashboard.html")[0], 200)

    def alive(self, port):
        try:
            return self.get(port, "dashboard.html")[0] == 200
        except OSError:
            return False

    def test_bare_call_after_finish_comes_back_on_the_same_port(self):
        """Открытая вкладка опрашивает прежний адрес: после finish сервер должен вернуться на него."""
        os.environ["AIDESIGN_STOP_DELAY"] = "1"
        self.addCleanup(os.environ.pop, "AIDESIGN_STOP_DELAY", None)
        self.init()
        self.assertEqual(self.ad(serve=True)[0], 0)
        port = self.pid()[0]
        self.ok("finish", "--result", "готово")
        time.sleep(2.5)
        self.assertFalse(self.alive(port), "finish должен погасить сервер")
        code, out = self.ad(serve=True)
        self.assertEqual(code, 0, out)
        self.assertIn("http://localhost:%d/dashboard.html" % port, out)
        self.assertTrue(self.alive(port))

    def test_finish_stops_server_and_bare_call_brings_history_back(self):
        """Превью видны только по http: сданный прогон смотрят через сервер, который
        поднимает голый вызов ad.py. Отложенная остановка от finish его не гасит."""
        os.environ["AIDESIGN_STOP_DELAY"] = "1"
        self.addCleanup(os.environ.pop, "AIDESIGN_STOP_DELAY", None)
        self.init()
        self.ok("round", "new")
        for oid in "abc":
            self.ok("round", "option", "--id", oid, "--title", oid.upper(), "--src", self.preview(1, oid))
        self.ok("round", "choose", "--id", "b")
        self.assertEqual(self.ad(serve=True)[0], 0)
        port = self.pid()[0]
        self.ok("finish", "--result", "готово")
        time.sleep(2.5)
        self.assertFalse(self.alive(port), "finish должен погасить сервер")
        code, out = self.ad(serve=True)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"http://localhost:\d+/dashboard\.html")
        port = self.pid()[0]
        self.ok("finish", "--result", "готово")   # повторный finish: отложенная остановка
        self.ad(serve=True)                        # …которую голый вызов отменяет
        time.sleep(2.5)
        port = self.pid()[0]
        done = self.state()["dir"]
        self.assertTrue(self.alive(port))
        self.assertFalse(done.endswith("--wip"))
        self.assertEqual(self.get(port, "%s/rounds/01/b.html" % done)[0], 200)
        self.assertEqual(self.get(port, "examples/INDEX.json")[0], 200)

    def test_stale_stop_does_not_kill_a_server_asked_for_again(self):
        """Гонка 1: остановка помнит, чья она. Чужая отметка serve.stop — не повод гасить."""
        os.environ["AIDESIGN_STOP_DELAY"] = "0"
        self.addCleanup(os.environ.pop, "AIDESIGN_STOP_DELAY", None)
        self.init()
        self.assertEqual(self.ad(serve=True)[0], 0)
        port = self.pid()[0]
        write(os.path.join(self.a, "serve.stop"), "новая-остановка\n")
        self.ad("--stop-now", "старая-остановка")
        self.assertTrue(self.alive(port), "чужая остановка погасила сервер")
        self.assertTrue(os.path.exists(os.path.join(self.a, "serve.stop")))

    def test_bare_call_during_stopping_waits_and_brings_server_back(self):
        """Гонка 2: голый вызов в окне, когда остановка уже гасит сервер, не отдаёт
        адрес умирающего сервера, а дожидается и поднимает новый."""
        import threading
        self.init()
        self.assertEqual(self.ad(serve=True)[0], 0)
        port, pid = self.pid()
        stopping = os.path.join(self.a, "serve.stopping")
        write(stopping, "идёт остановка\n")

        def finish_stop():
            time.sleep(1.0)
            os.kill(pid, 15)
            time.sleep(0.3)
            write(os.path.join(self.a, "serve.pid"), "%d 0\n" % port)
            os.remove(stopping)

        t = threading.Thread(target=finish_stop)
        t.start()
        code, out = self.ad(serve=True)
        t.join()
        self.assertEqual(code, 0, out)
        time.sleep(0.3)
        self.assertTrue(self.alive(self.pid()[0]), out)


if __name__ == "__main__":
    unittest.main()
