"""Тесты skills/aidesign/tools/browser.py — общего браузерного модуля.

Шов — функции модуля и командная строка. Настоящий браузер не нужен: `node`, `npm` и `npx` —
поддельные программы во временной папке (AIDESIGN_BROWSER_PATH), общий кэш — временная папка
(AIDESIGN_BROWSER_HOME). Один живой тест запускает настоящий браузер и пропускается, если
модуль на этом компьютере не поставлен (`browser.py ensure --yes`).
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools")
BROWSER = os.path.join(TOOLS, "browser.py")
UNIX = os.name != "nt"


def load():
    spec = importlib.util.spec_from_file_location("aidesign_browser", BROWSER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path, text, exe=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if exe:
        os.chmod(path, 0o755)


# Поддельная программа: пишет аргументы в журнал, отвечает по режиму из файла рядом.
FAKE = """#!%s
import json, os, sys
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(%r, "a", encoding="utf-8") as f:
    f.write(name + " " + " ".join(args) + "\\n")
if name == "node" and args == ["--version"]:
    print("v22.11.0"); sys.exit(0)
if name == "npx":
    print("Version 1.65.1"); sys.exit(0)
if name == "npm":
    home = args[args.index("--prefix") + 1]
    os.makedirs(os.path.join(home, "node_modules", "playwright"), exist_ok=True)
    ver = [a for a in args if a.startswith("playwright@")][0].split("@", 1)[1]
    with open(os.path.join(home, "node_modules", "playwright", "package.json"), "w") as f:
        json.dump({"name": "playwright", "version": ver}, f)
    sys.exit(0)
mode = open(%r).read().strip()
if mode == "fail":
    sys.stdout.write(json.dumps({"ok": False, "error": "browserType.launch: Executable doesn't exist"}) + "\\n")
    sys.exit(1)
if mode == "garbage":
    print("это не JSON"); sys.exit(0)
if mode == "slow":
    import time; time.sleep(30)
payload = json.loads(args[1]) if len(args) > 1 else {}
sys.stdout.write("лог браузера\\n")
sys.stdout.write(json.dumps({"ok": True, "browser": "chromium", "version": "141.0", "echo": payload,
                             "home": os.environ.get("AIDESIGN_NODE_HOME")}) + "\\n")
"""


@unittest.skipUnless(UNIX, "поддельные node/npm — скрипты с #!")
class Browser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="browser-test-")
        self.bin = os.path.join(self.tmp, "bin")
        self.home = os.path.join(self.tmp, "cache", "node")
        self.calls = os.path.join(self.tmp, "calls.log")
        self.mode = os.path.join(self.tmp, "mode")
        write(self.mode, "ok")
        os.makedirs(self.bin)
        self.env = {k: v for k, v in os.environ.items()}
        os.environ["AIDESIGN_BROWSER_PATH"] = self.bin
        os.environ["AIDESIGN_BROWSER_HOME"] = self.home
        self.b = load()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, *names):
        for n in names:
            write(os.path.join(self.bin, n), FAKE % (sys.executable, self.calls, self.mode), exe=True)

    def log(self):
        return open(self.calls, encoding="utf-8").read() if os.path.exists(self.calls) else ""

    def cli(self, *args):
        env = dict(os.environ)
        return subprocess.run([sys.executable, BROWSER] + list(args), capture_output=True, text=True,
                              env=env, encoding="utf-8", timeout=60)

    def test_cache_dir_is_outside_the_project_and_overridable(self):
        self.assertEqual(self.b.cache_dir(), self.home)
        del os.environ["AIDESIGN_BROWSER_HOME"]
        default = self.b.cache_dir()
        self.assertTrue(default.startswith(os.path.expanduser("~")))
        self.assertIn("aidesign", default)
        self.assertFalse(default.startswith(os.path.dirname(HERE)))   # не в проекте

    def test_doctor_without_node_says_so_and_exits_1(self):
        r = self.cli("doctor")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Node.js", r.stdout)
        self.assertIn("setup.py", r.stdout)

    def test_doctor_json_reports_missing_package(self):
        self.fake("node", "npm", "npx")
        r = self.cli("doctor", "--json")
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        self.assertTrue(data["node"])
        self.assertIsNone(data["installed"])
        self.assertEqual(data["target"], "1.65.1")             # та же версия, что npx playwright
        self.assertFalse(data["ready"])

    def test_ensure_without_yes_only_prints_the_plan(self):
        self.fake("node", "npm", "npx")
        r = self.cli("ensure")
        self.assertEqual(r.returncode, 1)
        self.assertRegex(r.stdout, r"playwright\W1\.65\.1")       # пакет той же версии, что у npx
        self.assertIn("--yes", r.stdout)
        self.assertNotIn("npm install", self.log())          # ничего не поставлено
        self.assertFalse(os.path.exists(self.home))

    def test_ensure_yes_installs_once_into_the_cache_and_probes(self):
        self.fake("node", "npm", "npx")
        r = self.cli("ensure", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.log().count("npm install"), 1)
        self.assertIn("--prefix %s" % self.home, self.log())
        self.assertIn("probe.mjs", self.log())
        r2 = self.cli("ensure", "--yes")                       # второй раз — уже стоит
        self.assertEqual(r2.returncode, 0)
        self.assertEqual(self.log().count("npm install"), 1)

    def test_run_returns_the_last_json_line_and_passes_the_cache(self):
        self.fake("node", "npm", "npx")
        self.cli("ensure", "--yes")
        out = self.b.run("probe.mjs", {"x": 1}, timeout=20)
        self.assertTrue(out["ok"])
        self.assertEqual(out["echo"], {"x": 1})
        self.assertEqual(out["home"], self.home)

    def test_run_failure_raises_with_the_browser_error(self):
        self.fake("node", "npm", "npx")
        self.cli("ensure", "--yes")
        write(self.mode, "fail")
        with self.assertRaises(self.b.BrowserError) as e:
            self.b.run("probe.mjs", {}, timeout=20)
        self.assertIn("Executable doesn't exist", str(e.exception))
        write(self.mode, "garbage")
        with self.assertRaises(self.b.BrowserError):
            self.b.run("probe.mjs", {}, timeout=20)

    def test_run_timeout_raises(self):
        self.fake("node", "npm", "npx")
        self.cli("ensure", "--yes")
        write(self.mode, "slow")
        with self.assertRaises(self.b.BrowserError) as e:
            self.b.run("probe.mjs", {}, timeout=1)
        self.assertIn("1 с", str(e.exception))

    def test_run_without_package_points_to_ensure(self):
        self.fake("node", "npm", "npx")
        with self.assertRaises(self.b.BrowserError) as e:
            self.b.run("probe.mjs", {}, timeout=5)
        self.assertIn("ensure", str(e.exception))

    def test_browser_not_launching_shows_install_and_chrome_hint(self):
        self.fake("node", "npm", "npx")
        self.cli("ensure", "--yes")
        write(self.mode, "fail")
        r = self.cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("install chromium", r.stdout)
        self.assertIn("Chrome", r.stdout)

    def test_unknown_command_is_input_error(self):
        self.assertEqual(self.cli("fly").returncode, 2)


def live_ready():
    try:
        return load().ready()
    except Exception:  # noqa: BLE001 — нет модуля или кэша: живой тест пропускается
        return False


@unittest.skipUnless(live_ready(), "браузерный модуль не поставлен (browser.py ensure --yes)")
class LiveBrowser(unittest.TestCase):
    def test_probe_launches_a_real_browser(self):
        out = load().run("probe.mjs", {}, timeout=120)
        self.assertTrue(out["ok"], out)
        self.assertIn(out["browser"], ("chromium", "chrome", "msedge"))
        self.assertIn("AIDesign", out["userAgent"])              # честный User-Agent
        self.assertIn("HeadlessChrome", out["userAgent"])        # без маскировки под человека


if __name__ == "__main__":
    unittest.main()
