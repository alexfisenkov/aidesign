"""Тесты skills/aidesign/tools/extract.py — стиль сайта по ссылке.

Швы: `analyze(raw, …)` (разбор того, что снял браузер, — без браузера), `robots(url)` и
командная строка. Сайт — свой http-сервер в тесте на 127.0.0.1. Браузер в обычных тестах —
поддельный `node` (AIDESIGN_BROWSER_PATH), отдающий заранее снятый ответ. Живой тест запускает
настоящий браузер на тестовой странице и пропускается, если модуль не поставлен.
"""

import functools
import http.server
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools")
EXTRACT = os.path.join(TOOLS, "extract.py")
UNIX = os.name != "nt"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, file))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, TOOLS)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(TOOLS)
    return mod


def write(path, text, exe=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if exe:
        os.chmod(path, 0o755)


def el(tag, ctx="", n=1, **kw):
    base = {"tag": tag, "ctx": ctx or tag, "area": 2000, "text": True, "color": "#111111", "bg": None,
            "border": None, "ff": "Inter, system-ui, sans-serif", "fs": 16, "fw": "400", "lh": "24px",
            "radius": "0px", "shadow": None, "pad": [0, 0, 0, 0], "mar": [0, 0, 0, 0], "gap": [],
            "td": "0s", "tt": "ease", "ad": "0s", "at": "ease"}
    base.update(kw)
    return [dict(base) for _ in range(n)]


def snap(**kw):
    s = {"bg": None, "color": "#111111", "border": "0px none", "borderColor": None, "radius": "0px",
         "padding": "0px", "fs": 16, "fw": "400", "ff": "Inter, sans-serif", "shadow": None,
         "outline": "0px none", "outlineColor": None, "decoration": "none", "transition": "all 0s ease 0s"}
    s.update(kw)
    return s


def sample_raw():
    """Страница: много серого текста, серые секции, три оранжевые кнопки, бирюзовые ссылки."""
    els = []
    els += el("p", "p text muted", 60, color="#666666", pad=[0, 0, 16, 0], mar=[0, 0, 24, 0])
    els += el("section", "section block", 8, text=False, bg="#f2f2f2", area=400000, pad=[64, 32, 64, 32])
    els += el("h1", "h1 hero-title", 1, ff='"Playfair Display", Georgia, serif', fs=48, fw="700", lh="56px")
    els += el("h2", "h2", 4, ff='"Playfair Display", Georgia, serif', fs=32, fw="700", lh="40px", mar=[0, 0, 16, 0])
    els += el("button", "button btn btn-primary", 3, color="#ffffff", bg="#e4572e", radius="8px",
              pad=[12, 24, 12, 24], td="0.2s", tt="cubic-bezier(0.2, 0, 0, 1)", fw="600")
    els += el("a", "a link", 6, color="#2a9d8f", gap=[8, 8])
    els += el("div", "card", 4, text=False, bg="#ffffff", radius="16px", border="#e0e0e0", pad=[24, 24, 24, 24],
              gap=[16, 16])
    btn = {"base": snap(bg="#e4572e", color="#ffffff", radius="8px", padding="12px 24px", fw="600"),
           "hover": snap(bg="#c8431d", color="#ffffff", radius="8px", padding="12px 24px", fw="600"),
           "focus": snap(bg="#e4572e", color="#ffffff", radius="8px", padding="12px 24px", fw="600",
                         outline="2px solid", outlineColor="#2a9d8f")}
    return {"ok": True, "url": "https://example.test/", "finalUrl": "https://example.test/", "status": 200,
            "browser": "chromium", "viewport": {"w": 1280, "h": 800}, "consent": None, "total": len(els),
            "body": {"bg": "#ffffff", "color": "#111111"}, "vars": [], "elements": els,
            "buttons": [btn], "inputs": [{"base": snap(bg="#ffffff", border="1px solid", borderColor="#cccccc",
                                                       radius="8px"),
                                          "focus": snap(bg="#ffffff", border="1px solid", borderColor="#e4572e",
                                                        radius="8px")}],
            "links": [{"base": snap(color="#2a9d8f"), "hover": snap(color="#2a9d8f", decoration="underline")}],
            "media": ["(max-width: 768px)", "screen and (min-width: 64em)", "(prefers-reduced-motion: reduce)",
                      "(max-width: 768px)"],
            "fonts": ["Playfair Display", "Inter"]}


def roles(result):
    return {c["role"]: c for c in result["colors"]}


class Analyze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x = load("aidesign_extract", "extract.py")

    def analyze(self, raw):
        return self.x.analyze(raw, url="https://example.test/", robots="allowed")

    def test_primary_is_the_button_colour_not_the_common_grey(self):
        r = roles(self.analyze(sample_raw()))
        self.assertEqual(r["primary"]["hex"], "#e4572e")
        self.assertEqual(r["primary"]["on"], "#ffffff")
        self.assertEqual(r["primary"]["confidence"], "high")
        self.assertTrue(r["primary"]["oklch"].startswith("oklch("))

    def test_other_roles(self):
        r = roles(self.analyze(sample_raw()))
        self.assertEqual(r["background"]["hex"], "#ffffff")
        self.assertEqual(r["text"]["hex"], "#111111")
        self.assertEqual(r["accent"]["hex"], "#2a9d8f")
        self.assertEqual(r["surface"]["hex"], "#f2f2f2")
        self.assertEqual(r["text-muted"]["hex"], "#666666")
        self.assertEqual(r["border"]["hex"], "#e0e0e0")
        self.assertEqual(r["primary-hover"]["hex"], "#c8431d")
        self.assertEqual(r["focus"]["hex"], "#2a9d8f")

    def test_monochrome_site_takes_the_shared_button_fill(self):
        raw = sample_raw()
        raw["elements"] = [e for e in raw["elements"] if e["tag"] not in ("button", "a")]
        raw["elements"] += el("button", "button btn", 3, bg="#000000", color="#ffffff")
        raw["buttons"] = []
        self.assertEqual(roles(self.analyze(raw))["primary"]["hex"], "#000000")

    def test_grey_buttons_do_not_win_logo_colour_does(self):
        raw = sample_raw()
        raw["elements"] = [e for e in raw["elements"] if e["tag"] not in ("button", "a")]
        raw["elements"] += el("button", "button btn", 4, bg="#f2f2f2", color="#222222")
        raw["elements"] += el("svg", "svg", 1, text=False, fill="#ff385c", logo=True)
        raw["buttons"] = []
        raw["vars"] = [{"name": "--palette-bg-primary-disabled", "value": "#f2f2f2", "hex": "#f2f2f2"}]
        r = roles(self.analyze(raw))
        self.assertEqual(r["primary"]["hex"], "#ff385c")
        self.assertEqual(r["primary"]["why"], "цвет логотипа")

    def test_typography(self):
        t = self.analyze(sample_raw())["typography"]
        fam = {f["use"]: f["name"] for f in t["families"]}
        self.assertEqual(fam["heading"], "Playfair Display")
        self.assertEqual(fam["body"], "Inter")
        self.assertEqual([s["px"] for s in t["scale"]][:3], [48, 32, 16])
        self.assertIn("700", [w["weight"] for w in t["weights"]])
        self.assertIn(1.5, [h["ratio"] for h in t["lineHeights"]])

    def test_spacing_radius_motion_breakpoints(self):
        r = self.analyze(sample_raw())
        values = [s["px"] for s in r["spacing"]]
        for v in (16, 24, 64):
            self.assertIn(v, values)
        self.assertEqual(r["spacingBase"], 8)
        self.assertEqual([x["value"] for x in r["radius"]], ["8px", "16px"])
        self.assertIn("200ms", [d["value"] for d in r["motion"]["durations"]])
        self.assertIn("cubic-bezier(0.2, 0, 0, 1)", [e["value"] for e in r["motion"]["easings"]])
        self.assertEqual([b["px"] for b in r["breakpoints"]], [768, 1024])
        self.assertEqual(r["shadows"], [])

    def test_components_with_states(self):
        c = self.analyze(sample_raw())["components"]
        self.assertEqual(c["buttons"][0]["states"]["hover"]["bg"], "#c8431d")
        self.assertEqual(c["buttons"][0]["states"]["focus"]["outlineColor"], "#2a9d8f")
        self.assertEqual(c["inputs"][0]["states"]["focus"]["borderColor"], "#e4572e")
        self.assertEqual(c["links"][0]["states"]["hover"]["decoration"], "underline")

    def test_missing_is_named(self):
        r = self.analyze(sample_raw())
        self.assertIn("тени", r["missing"])
        self.assertNotIn("кнопки", r["missing"])
        self.assertEqual(r["source"]["domain"], "example.test")
        self.assertEqual(r["source"]["robots"], "allowed")

    def test_dark_theme_by_flag(self):
        raw = sample_raw()
        dark = sample_raw()
        dark["body"] = {"bg": "#101418", "color": "#eeeeee"}
        raw["dark"] = dark
        r = self.analyze(raw)
        self.assertTrue(r["dark"]["differs"])
        self.assertEqual(roles(r["dark"])["background"]["hex"], "#101418")
        self.assertIsNone(self.analyze(sample_raw())["dark"])

    def test_tokens_css_is_our_format_and_passes_designsystem_export(self):
        r = self.analyze(dict(sample_raw(), dark=dict(sample_raw(), body={"bg": "#101418", "color": "#eeeeee"})))
        css = self.x.tokens_css(r)
        self.assertIn("снято с example.test", css)
        self.assertIn("принципы, не бренд", css)
        self.assertIn("не наблюдалось: тени", css)
        tmp = tempfile.mkdtemp(prefix="extract-ds-")
        try:
            write(os.path.join(tmp, "design-system", "tokens.css"), css)
            ds = load("aidesign_designsystem", "designsystem.py")
            with open(ds.export(tmp), encoding="utf-8") as f:
                data = json.load(f)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(data["color"]["primary"], "#e4572e")
        self.assertIn("heading", data["font"])
        self.assertTrue(data["space"])
        self.assertTrue(data["radius"])
        self.assertTrue(data["motion"])
        self.assertEqual(data["other"], {})
        self.assertEqual(data["$themes"]["dark"]["color"]["bg"], "#101418")

    def test_own_site_is_called_yours_without_brand_warnings(self):
        r = self.x.analyze(sample_raw(), url="https://example.test/", robots="own-site")
        css, md = self.x.tokens_css(r), self.x.report_md(r)
        for text in (css, md):
            self.assertIn("вашего сайта", text)
            self.assertNotIn("не бренд", text)
            self.assertNotIn("замените", text)
        self.assertIn("AI Design: снято с", css[:400])          # свой прошлый результат узнаётся
        self.assertTrue(md.startswith("# Стиль с "))
        foreign = self.analyze(sample_raw())
        self.assertIn("не бренд", self.x.tokens_css(foreign))

    def test_fallback_font_follows_the_category(self):
        raw = sample_raw()
        for e in raw["elements"]:
            if e["tag"] in ("h1", "h2"):
                e["ff"] = '"Playfair Display", "PT Serif"'
            elif e.get("text"):
                e["ff"] = '"JetBrains Mono"'
        css = self.x.tokens_css(self.analyze(raw))
        self.assertIn('--font-heading: "Playfair Display", "PT Serif", serif;', css)
        self.assertIn('--font-body: "JetBrains Mono", monospace;', css)
        raw = sample_raw()
        for e in raw["elements"]:
            if e.get("text"):
                e["ff"] = '"Noto Serif Display"' if e["tag"] in ("h1", "h2") else '"Some Unknown Grotesk"'
        css = self.x.tokens_css(self.analyze(raw))
        self.assertIn('"Noto Serif Display", serif;', css)
        self.assertIn('"Some Unknown Grotesk", sans-serif;', css)


class Guard(unittest.TestCase):
    """Адреса и robots.txt: чистые функции, без сети (адреса — числами)."""

    @classmethod
    def setUpClass(cls):
        cls.x = load("aidesign_extract_guard", "extract.py")

    def test_internal_addresses(self):
        for host in ("127.0.0.1", "10.0.0.5", "172.31.255.1", "192.168.1.1", "169.254.169.254", "100.64.0.1",
                     "0.0.0.0", "224.0.0.1", "::1", "fc00::1", "fd12::1", "fe80::1", "::ffff:10.0.0.1", "::"):
            self.assertTrue(self.x.address_problem("http://[%s]/" % host if ":" in host else "http://%s/" % host),
                            host)
        for url in ("http://0177.0.0.1/", "http://0x7f.0.0.1/", "http://127.1/", "http://2130706433/",
                    "http://0x7f000001/", "http://[::7f00:1]/", "http://[::ffff:7f00:1]/"):
            self.assertTrue(self.x.address_problem(url), url)       # запись IPv4, как её понимает браузер
        self.assertEqual(self.x.normalize("http://0177.0.0.1:8080/a?b"), "http://127.0.0.1:8080/a?b")
        self.assertEqual(self.x.normalize("example.com/x"), "https://example.com/x")
        for host in ("93.184.215.14", "2606:4700::1111"):
            self.assertIsNone(self.x.address_problem("http://[%s]/" % host if ":" in host else "http://%s/" % host),
                              host)

    def test_robots_rules_rfc9309(self):
        allows = self.x.robots_allows
        txt = "User-agent: *\nDisallow: /private\nAllow: /private/open\nDisallow: /*.pdf$\n"
        self.assertFalse(allows(txt, "http://h/private/x"))
        self.assertTrue(allows(txt, "http://h/private/open/x"))
        self.assertFalse(allows(txt, "http://h/files/a.pdf"))
        self.assertTrue(allows(txt, "http://h/files/a.pdf?x=1"))
        self.assertTrue(allows(txt, "http://h/"))
        ours = "User-agent: *\nAllow: /\n\nUser-Agent: aidesign\nDisallow: /x\n"
        self.assertFalse(allows(ours, "http://h/x/1"))
        self.assertTrue(allows("User-agent: *\nDisallow:\n", "http://h/a"))


@unittest.skipUnless(shutil.which("node"), "нет node")
class ConsentWords(unittest.TestCase):
    """Слова кнопки «принять» — целиком, без хвостов (browser/consent.mjs, без браузера)."""

    def labels(self, words):
        mod = pathlib.Path(TOOLS, "browser", "consent.mjs").as_uri()
        code = "import {isAccept} from %s; console.log(JSON.stringify(%s.map(isAccept)))" % (
            json.dumps(mod), json.dumps(words, ensure_ascii=False))
        r = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return dict(zip(words, json.loads(r.stdout)))

    def test_browser_guard_addresses(self):
        mod = pathlib.Path(TOOLS, "browser", "guard.mjs").as_uri()
        inside = ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::", "::7f00:1", "::ffff:7f00:1", "fe80::1",
                  "fd00::1", "100.64.0.1"]
        outside = ["8.8.8.8", "93.184.215.14", "2606:4700::1111", "::ffff:808:808"]
        code = "import {internalIp} from %s; console.log(JSON.stringify(%s.map(internalIp)))" % (
            json.dumps(mod), json.dumps(inside + outside))
        r = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [True] * len(inside) + [False] * len(outside))

    def test_answer_from_an_internal_address_stops_the_run(self):
        """Подмена DNS: сторож проверил имя, а браузер получил ответ с внутреннего адреса."""
        mod = pathlib.Path(TOOLS, "browser", "guard.mjs").as_uri()
        cases = [[{"ipAddress": "127.0.0.1", "port": 80}, {}], [{"ipAddress": "10.1.2.3", "port": 443}, {}],
                 [{"ipAddress": "::ffff:7f00:1", "port": 80}, {}], [{"ipAddress": "93.184.215.14", "port": 443}, {}],
                 [None, {}], [{"ipAddress": "127.0.0.1", "port": 80}, {"allowLocal": True}]]
        code = ("import {answerProblem} from %s; const c = %s;"
                "console.log(JSON.stringify(c.map(([a, o]) => answerProblem(a, 'https://example.test/x.css', o))))"
                % (json.dumps(mod), json.dumps(cases)))
        r = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        for why in got[:3]:
            self.assertIn("внутренн", why)
            self.assertIn("example.test", why)
        self.assertEqual(got[3:], [None, None, None])

    def test_whole_words_only(self):
        yes = ["Принять", "  принять все ", "Принять всё!", "Принять cookies", "Согласен", "OK", "Ok.", "Accept",
               "Accept all", "Accept All Cookies", "Allow all", "Got it!", "Agree", "I agree", "Понятно"]
        no = ["Принять приглашение", "OK, delete my account", "Accept invitation", "Не согласен", "Disagree",
              "Reject all", "Cookies Settings", "Настроить", "Отказаться", "Вступить", "Okay then delete", ""]
        got = self.labels(yes + no)
        self.assertEqual([w for w in yes if not got[w]], [])
        self.assertEqual([w for w in no if got[w]], [])


# ── сайт в тесте ────────────────────────────────────────────────────────────

class Quiet(http.server.SimpleHTTPRequestHandler):
    redirects = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in self.redirects:
            self.send_response(302)
            self.send_header("Location", self.redirects[self.path])
            self.end_headers()
            return
        super().do_GET()


class Site:
    def __init__(self, root, redirects=None):
        handler = functools.partial(type("H", (Quiet,), {"redirects": redirects or {}}), directory=root)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = "http://127.0.0.1:%d/" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


FAKE_NODE = """#!%s
import json, os, sys
open(os.path.join(os.path.dirname(%r), "args.json"), "w", encoding="utf-8").write(sys.argv[2])
sys.stdout.write(json.dumps(json.load(open(%r, encoding="utf-8"))) + "\\n")
"""


@unittest.skipUnless(UNIX, "поддельный node — скрипт с #!")
class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="extract-test-")
        self.www = os.path.join(self.tmp, "www")
        write(os.path.join(self.www, "index.html"), "<!doctype html><title>t</title>")
        self.site = Site(self.www)
        self.bin = os.path.join(self.tmp, "bin")
        self.home = os.path.join(self.tmp, "cache")
        write(os.path.join(self.home, "node_modules", "playwright", "package.json"), '{"version": "1.65.1"}')
        raw = os.path.join(self.tmp, "raw.json")
        write(raw, json.dumps(sample_raw()))
        write(os.path.join(self.bin, "node"), FAKE_NODE % (sys.executable, raw, raw), exe=True)
        self.args = os.path.join(self.tmp, "args.json")
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        self.site.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args):
        env = dict(os.environ, AIDESIGN_BROWSER_PATH=self.bin, AIDESIGN_BROWSER_HOME=self.home)
        return subprocess.run([sys.executable, EXTRACT] + list(args), capture_output=True, text=True,
                              env=env, encoding="utf-8", timeout=60, cwd=self.tmp)

    def test_local_address_is_refused_without_a_flag(self):
        r = self.cli(self.site.url, "--out", self.out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("внутренн", r.stdout + r.stderr)
        self.assertIn("--allow-local", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.args))                 # браузер не запускался
        self.assertFalse(os.path.exists(self.out))

    def test_cloud_metadata_and_private_ranges_are_refused(self):
        for url in ("http://169.254.169.254/latest/meta-data/", "http://localhost/", "http://10.1.2.3/",
                    "http://192.168.0.1/", "http://172.20.0.1/", "http://[::1]/", "http://[fd00::1]/",
                    "http://[fe80::1]/", "http://[::ffff:127.0.0.1]/", "http://0.0.0.0/", "http://100.64.0.1/"):
            r = self.cli(url, "--out", self.out)
            self.assertEqual(r.returncode, 1, url + r.stdout + r.stderr)
            self.assertIn("внутренн", r.stdout + r.stderr, url)
        self.assertFalse(os.path.exists(self.args))

    def test_flags_reach_the_browser_guard(self):
        self.assertEqual(self.cli(self.site.url, "--allow-local", "--out", self.out).returncode, 0)
        sent = json.load(open(self.args, encoding="utf-8"))
        self.assertEqual((sent["allowLocal"], sent["ownSite"]), (True, False))

    def test_robots_disallow_stops_with_code_1(self):
        write(os.path.join(self.www, "robots.txt"), "User-agent: *\nDisallow: /\n")
        r = self.cli(self.site.url, "--allow-local", "--out", self.out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("robots.txt", r.stdout + r.stderr)
        self.assertIn("--own-site", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_robots_disallow_for_our_agent_only(self):
        write(os.path.join(self.www, "robots.txt"), "User-agent: AIDesign\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
        self.assertEqual(self.cli(self.site.url, "--allow-local", "--out", self.out).returncode, 1)

    def test_robots_longest_match_wins(self):
        write(os.path.join(self.www, "robots.txt"), "User-agent: *\nAllow: /\nDisallow: /index\n")
        r = self.cli(self.site.url + "index.html", "--allow-local", "--out", self.out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_own_site_lifts_robots_and_writes_three_files(self):
        write(os.path.join(self.www, "robots.txt"), "User-agent: *\nDisallow: /\n")
        r = self.cli(self.site.url, "--own-site", "--out", self.out, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["robots"], "own-site")
        sent = json.load(open(self.args, encoding="utf-8"))
        self.assertEqual((sent["allowLocal"], sent["ownSite"]), (True, True))
        for name in ("extract.json", "report.md", "tokens.css"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, name)), name)
        data = json.load(open(os.path.join(self.out, "extract.json"), encoding="utf-8"))
        self.assertEqual(roles(data)["primary"]["hex"], "#e4572e")
        self.assertIn("основной", open(os.path.join(self.out, "report.md"), encoding="utf-8").read())

    def test_no_robots_file_is_allowed(self):
        r = self.cli(self.site.url, "--allow-local", "--out", self.out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.load(open(os.path.join(self.out, "extract.json"), encoding="utf-8"))
        self.assertEqual(data["source"]["robots"], "no-file")

    def test_foreign_files_are_not_overwritten(self):
        for name, text in (("tokens.css", ":root{--color-x:#000}"), ("extract.json", '{"mine": 1}'),
                           ("report.md", "# Мой отчёт\n")):
            out = os.path.join(self.tmp, "out-" + name)
            write(os.path.join(out, name), text)
            r = self.cli(self.site.url, "--allow-local", "--out", out)
            self.assertEqual(r.returncode, 1, name)
            self.assertIn("не перезаписываю", r.stdout + r.stderr)
            self.assertEqual(open(os.path.join(out, name), encoding="utf-8").read(), text)
            self.assertEqual(sorted(os.listdir(out)), [name])

    def test_own_previous_result_is_refreshed(self):
        self.assertEqual(self.cli(self.site.url, "--allow-local", "--out", self.out).returncode, 0)
        self.assertEqual(self.cli(self.site.url, "--allow-local", "--out", self.out).returncode, 0)

    def test_bad_url_is_input_error(self):
        self.assertEqual(self.cli("ftp://example.test/").returncode, 2)
        self.assertEqual(self.cli("file:///etc/hosts").returncode, 2)

    def test_browser_not_ready_names_ensure(self):
        shutil.rmtree(self.home)
        r = self.cli(self.site.url, "--allow-local", "--out", self.out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("browser.py ensure", r.stdout + r.stderr)


# ── живой браузер на тестовой странице ──────────────────────────────────────

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Тест</title>
<style>
:root{--brand:#e4572e}
body{margin:0;background:#fbfaf7;color:#1d1d1f;font:16px/1.5 Georgia,serif}
h1{font:700 52px/1.1 Arial,sans-serif;margin:0 0 24px}
h2{font:600 28px/1.2 Arial,sans-serif;margin:0 0 16px}
p{color:#5c5c5c;margin:0 0 16px}
section{padding:64px 32px}
.card{background:#ffffff;border:1px solid #e5e2dc;border-radius:16px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.08)}
.btn{background:#e4572e;color:#fff;border:0;border-radius:10px;padding:12px 24px;font-weight:600;
     transition:background-color .2s cubic-bezier(.2,0,0,1)}
.btn:hover{background:#b8401b}
.btn:focus-visible,.btn:focus{outline:3px solid #2a6f97;outline-offset:2px}
a{color:#2a6f97}
a:hover{text-decoration:underline}
input{border:1px solid #c9c4bb;border-radius:10px;padding:10px 12px;background:#fff}
input:focus{border-color:#e4572e;outline:none}
#cookies{position:fixed;inset:auto 0 0 0;background:#222;color:#fff;padding:16px}
@media (max-width: 720px){h1{font-size:36px}}
@media (min-width: 1100px){section{padding:96px 48px}}
@media (prefers-color-scheme: dark){body{background:#121212;color:#ececec}}
</style></head><body>
<section><h1>Заголовок</h1><p>Текст абзаца.</p><p>Ещё абзац.</p>
<button class="btn">Записаться</button> <button class="btn">Подробнее о курсе</button>
<a class="btn" href="#x">Купить</a> <a href="#y">Ссылка</a> <a href="#z">Ещё ссылка</a>
<input placeholder="Почта"></section>
<section><h2>Раздел</h2><div class="card"><h2>Карточка</h2><p>Текст.</p></div>
<div class="card"><h2>Карточка</h2><p>Текст.</p></div></section>
<div id="cookies">Мы используем cookie.
<button id="settings" onclick="document.body.dataset.clicked='settings'">Настроить</button>
<button id="reject" class="consent-reject" onclick="document.body.dataset.clicked='reject'">Отказаться</button>
<button id="accept" onclick="document.body.dataset.clicked='accept';this.parentNode.remove()">Принять</button></div>
</body></html>"""


def live_ready():
    try:
        return load("aidesign_browser_probe", "browser.py").ready()
    except Exception:  # noqa: BLE001
        return False


# Ловушки: ни одна кнопка не в окне cookies — нажатие любой красит фон в красный или уводит на /joined.html.
TRAPS = """<!doctype html><html><head><meta charset="utf-8"><title>Ловушки</title>
<style>body{background:#fbfaf7;color:#1d1d1f}.cta{background:#1e6091;color:#fff}</style></head><body>
<p>Мы используем cookie, чтобы сайт работал.</p>
<button class="disagree cta" onclick="document.body.dataset.clicked='disagree';document.body.style.background='#ff0000'">Disagree</button>
<button class="agree cta" onclick="document.body.dataset.clicked='agree';document.body.style.background='#ff0000'">Не согласен</button>
<form action="/joined.html"><button id="accept-invite" class="cta" type="submit">Вступить</button></form>
<button data-testid="accept-terms" class="cta" onclick="document.body.style.background='#ff0000'">Принять приглашение</button>
<div role="dialog" aria-label="cookies">Файлы cookie помогают нам.
<button class="cta" id="agree-bad" onclick="document.body.style.background='#ff0000'">Не согласен</button></div>
</body></html>"""
JOINED = "<!doctype html><html><body style='background:#00ff00'>вступили</body></html>"
# Ловушки второго ревью: класс про cookies на body, AEM-обёртка cmp-container, «принять»/«OK» с хвостом.
TRAP_PAGES = {
    "body.html": """<!doctype html><html><head><meta charset=utf-8><style>body{background:#fbfaf7}</style></head>
<body class="cookie-consent-pending"><p>Наш сайт. Политика конфиденциальности, cookie.</p>
<form action="/joined.html"><button type="submit">Принять приглашение</button></form></body></html>""",
    "aem.html": """<!doctype html><html><head><meta charset=utf-8><style>body{background:#fbfaf7}</style></head>
<body><div class="cmp-container"><p>Главная. Privacy policy. Cookies.</p>
<button onclick="location.href='/joined.html'">OK, delete my account</button></div></body></html>""",
    "sticky.html": """<!doctype html><html><head><meta charset=utf-8><style>body{background:#fbfaf7}
header{position:sticky;top:0}</style></head><body><header><a href="/p">Privacy</a> cookies
<form action="/joined.html"><button type=submit>Accept invitation</button></form></header><p>x</p></body></html>""",
    "wrap.html": """<!doctype html><html><head><meta charset=utf-8><style>body{background:#fbfaf7;margin:0}
#cookie-wrap{min-height:100vh}</style></head><body><div id="cookie-wrap"><p>Сайт. Мы используем cookie.</p>
<button onclick="location.href='/joined.html'">OK</button></div></body></html>""",
}
# Настоящее окно, как у OneTrust: «Cookies Settings» не нажимается, «Accept All Cookies» — да.
ONETRUST = """<!doctype html><html><head><meta charset=utf-8><style>body{background:#fbfaf7;margin:0}
#onetrust-banner-sdk{position:fixed;left:0;right:0;bottom:0;background:#222;color:#fff;padding:16px}</style></head>
<body><p>Сайт.</p><div id="onetrust-consent-sdk"><div id="onetrust-banner-sdk" role="region">
We use cookies to improve your experience.
<button id="onetrust-pc-btn-handler" onclick="location.href='/joined.html'">Cookies Settings</button>
<button id="onetrust-accept-btn-handler" onclick="document.getElementById('onetrust-consent-sdk').remove()">Accept All Cookies</button>
</div></div></body></html>"""


@unittest.skipUnless(live_ready(), "браузерный модуль не поставлен (browser.py ensure --yes)")
class Live(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="extract-live-")
        www = os.path.join(self.tmp, "www")
        write(os.path.join(www, "index.html"), PAGE)
        write(os.path.join(www, "traps.html"), TRAPS)
        write(os.path.join(www, "joined.html"), JOINED)
        write(os.path.join(www, "onetrust.html"), ONETRUST)
        for name, html in TRAP_PAGES.items():
            write(os.path.join(www, name), html)
        write(os.path.join(www, "private", "page.html"), PAGE)
        write(os.path.join(www, "robots.txt"), "User-agent: *\nDisallow: /private\n")
        self.site = Site(www, {"/a": "/b", "/b": "/private/page.html", "/ok": "/index.html"})
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        self.site.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def extract(self, path, *flags):
        return subprocess.run([sys.executable, EXTRACT, self.site.url + path, "--out", self.out, "--json"] + list(flags),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)

    def test_redirect_into_a_disallowed_path_stops(self):
        r = self.extract("a", "--allow-local")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("robots.txt", r.stdout)
        self.assertIn("/private/page.html", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.out, "extract.json")))

    def test_redirect_into_an_allowed_path_goes_on(self):
        r = self.extract("ok", "--allow-local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_browser_guard_refuses_local_address_without_flag(self):
        # Сторож браузера сам, без проверки extract.py: переход главного фрейма на внутренний адрес.
        b = load("aidesign_browser_guard", "browser.py")
        with self.assertRaises(b.BrowserError) as e:
            b.run("extract.mjs", {"url": self.site.url + "ok", "allowLocal": False, "ownSite": True}, timeout=120)
        self.assertIn("внутренн", str(e.exception))

    def test_cookie_traps_are_not_pressed(self):
        r = self.extract("traps.html", "--allow-local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.load(open(os.path.join(self.out, "extract.json"), encoding="utf-8"))
        self.assertIsNone(data["source"]["consent"])
        self.assertEqual(roles(data)["background"]["hex"], "#fbfaf7")        # ни одна ловушка не нажата
        self.assertTrue(data["source"]["finalUrl"].endswith("/traps.html"))  # форма не отправлена

    def test_page_wrappers_and_tails_are_not_consent(self):
        for name in TRAP_PAGES:
            out = os.path.join(self.tmp, "out-" + name)
            r = subprocess.run([sys.executable, EXTRACT, self.site.url + name, "--out", out, "--json",
                                "--allow-local"], capture_output=True, text=True, encoding="utf-8", timeout=300)
            self.assertEqual(r.returncode, 0, name + r.stdout + r.stderr)
            data = json.load(open(os.path.join(out, "extract.json"), encoding="utf-8"))
            self.assertIsNone(data["source"]["consent"], name)
            self.assertTrue(data["source"]["finalUrl"].endswith("/" + name), name)   # адрес не сменился

    def test_onetrust_like_banner_is_accepted(self):
        r = self.extract("onetrust.html", "--allow-local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.load(open(os.path.join(self.out, "extract.json"), encoding="utf-8"))
        self.assertEqual(data["source"]["consent"]["text"], "Accept All Cookies")
        self.assertTrue(data["source"]["finalUrl"].endswith("/onetrust.html"))

    def test_real_browser_reads_the_test_page(self):
        r = subprocess.run([sys.executable, EXTRACT, self.site.url, "--dark", "--out", self.out, "--json",
                            "--allow-local"], capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.load(open(os.path.join(self.out, "extract.json"), encoding="utf-8"))
        rl = roles(data)
        self.assertEqual(rl["primary"]["hex"], "#e4572e")
        self.assertEqual(rl["primary-hover"]["hex"], "#b8401b")
        self.assertEqual(rl["background"]["hex"], "#fbfaf7")
        self.assertEqual(data["source"]["consent"]["text"], "Принять")      # не «Отказаться» и не «Настроить»
        self.assertEqual([b["px"] for b in data["breakpoints"]], [720, 1100])
        self.assertIn(52, [s["px"] for s in data["typography"]["scale"]])
        self.assertTrue(data["shadows"])
        self.assertEqual(data["components"]["inputs"][0]["states"]["focus"]["borderColor"], "#e4572e")
        self.assertTrue(data["dark"]["differs"])
        self.assertEqual(roles(data["dark"])["background"]["hex"], "#121212")


if __name__ == "__main__":
    unittest.main()
