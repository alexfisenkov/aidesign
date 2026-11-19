"""Тесты skills/aidesign/tools/shots.py — снимков превью 1280 и 390.

Шов — командная строка. Настоящий браузер не запускается: `npx` — поддельная программа
во временной папке (AIDESIGN_SHOTS_PATH): пишет аргументы в журнал и кладёт «снимок».
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools", "shots.py")
UNIX = os.name != "nt"

# Поддельный npx: пишет аргументы в журнал и кладёт «снимок» в последний аргумент.
FAKE_NPX = """#!%s
import sys
args = sys.argv[1:]
with open(%r, "a", encoding="utf-8") as f:
    f.write(" ".join(args) + "\\n")
mode = %r
if mode == "broken" or (mode == "no-bundled" and "--channel" not in args):
    sys.stderr.write("Error: browserType.launch: Executable doesn't exist at /x/chrome-headless-shell\\n")
    sys.stderr.write("\\u2554\\u2550\\u2550\\u2557\\n\\u255a\\u2550\\u2550\\u255d\\n")
    sys.exit(1)
with open(args[-1], "wb") as f:
    f.write(b"\\x89PNG\\r\\n\\x1a\\n")
"""


def write(path, text, exe=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if exe:
        os.chmod(path, 0o755)


@unittest.skipUnless(UNIX, "поддельный npx — скрипт с #!")
class Shots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shots-test-")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.calls = os.path.join(self.tmp, "calls.log")
        self.page = os.path.join(self.tmp, "rounds", "01", "a.html")
        write(self.page, "<!doctype html><title>a</title>")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def npx(self, mode="ok"):
        write(os.path.join(self.bin, "npx"), FAKE_NPX % (sys.executable, self.calls, mode), exe=True)

    def run_shots(self, *args):
        env = dict(os.environ, AIDESIGN_SHOTS_PATH=self.bin)
        r = subprocess.run([sys.executable, "-B", SHOTS] + list(args), capture_output=True, text=True,
                           encoding="utf-8", env=env, cwd=self.tmp, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def test_two_shots_next_to_the_preview_at_1280_and_390(self):
        self.npx()
        code, out = self.run_shots(self.page, "--json")
        self.assertEqual(code, 0, out)
        got = json.loads(out)
        base = os.path.join(self.tmp, "rounds", "01")
        self.assertEqual(got["shots"], [{"file": self.page, "shot1280": os.path.join(base, "a-1280.png"),
                                         "shot390": os.path.join(base, "a-390.png")}])
        self.assertTrue(os.path.isfile(os.path.join(base, "a-1280.png")))
        self.assertTrue(os.path.isfile(os.path.join(base, "a-390.png")))
        with open(self.calls, encoding="utf-8") as f:
            calls = f.read()
        self.assertIn("playwright screenshot", calls)
        self.assertIn("1280,800", calls)
        self.assertIn("390,844", calls)
        self.assertIn("file://", calls)

    def test_without_npx_says_so_and_exits_1(self):
        code, out = self.run_shots(self.page)
        self.assertEqual(code, 1, out)
        self.assertIn("Playwright", out)
        self.assertIn("Открыть в новой вкладке", out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "rounds", "01", "a-1280.png")))

    def test_without_bundled_chromium_falls_back_to_installed_chrome(self):
        self.npx("no-bundled")
        code, out = self.run_shots(self.page)
        self.assertEqual(code, 0, out)
        with open(self.calls, encoding="utf-8") as f:
            calls = f.read()
        self.assertIn("--no-install", calls)               # пакет из сети тихо не качаем
        self.assertIn("--channel chrome", calls)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "rounds", "01", "a-390.png")))

    def test_broken_browser_is_a_refusal_not_a_crash(self):
        self.npx("broken")
        code, out = self.run_shots(self.page, "--json")
        self.assertEqual(code, 1, out)
        got = json.loads(out)
        self.assertEqual(got["shots"], [])
        self.assertIn("Executable doesn't exist", got["error"])     # строка ошибки, а не рамка из ═
        self.assertIn("npx playwright install chromium", got["error"])

    def test_missing_file_is_input_error(self):
        self.npx()
        code, out = self.run_shots(os.path.join(self.tmp, "нет.html"))
        self.assertEqual(code, 2, out)


if __name__ == "__main__":
    unittest.main()
