"""Тесты skills/aidesign/tools/setup.py — оснащения компьютера.

Шов — командная строка. Настоящая установка не запускается никогда:
`doctor` и `install` видят только подменённый PATH (AIDESIGN_SETUP_PATH) с
поддельными программами во временной папке, а `plan --os` не зависит от машины.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools", "setup.py")
IDS = ["python", "git", "node", "playwright", "ffmpeg", "webp", "figma"]
UNIX = os.name != "nt"


def write(path, text, exe=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if exe:
        os.chmod(path, 0o755)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="setup-test-")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.browsers = os.path.join(self.tmp, "browsers")
        os.makedirs(self.browsers)
        self.calls = os.path.join(self.tmp, "calls.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, name, out="", code=0):
        """Поддельная программа: пишет свои аргументы в calls.log и печатает out."""
        write(os.path.join(self.bin, name),
              "#!/bin/sh\necho \"%s $*\" >> \"%s\"\necho \"%s\"\nexit %d\n" % (name, self.calls, out, code), exe=True)

    def run_setup(self, *args, **extra_env):
        env = dict(os.environ, AIDESIGN_SETUP_PATH=self.bin, PLAYWRIGHT_BROWSERS_PATH=self.browsers, **extra_env)
        r = subprocess.run([sys.executable, "-B", SETUP] + list(args), capture_output=True, text=True,
                           encoding="utf-8", env=env, cwd=self.tmp, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def run_install(self, *args, **extra_env):
        """install видит только настоящий PATH: подмена AIDESIGN_SETUP_PATH ему запрещена."""
        env = {k: v for k, v in os.environ.items() if k != "AIDESIGN_SETUP_PATH"}
        env.update(PATH=self.bin, PLAYWRIGHT_BROWSERS_PATH=self.browsers, **extra_env)
        r = subprocess.run([sys.executable, "-B", SETUP, "install"] + list(args), capture_output=True, text=True,
                           encoding="utf-8", env=env, cwd=self.tmp, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def called(self):
        try:
            with open(self.calls, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def plan(self, *args):
        code, out = self.run_setup("plan", *args, "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)


@unittest.skipUnless(UNIX, "поддельные программы — shell-скрипты")
class Doctor(Base):
    def test_missing_git_gives_code_1_and_install_hint(self):
        self.fake("node", "v20.11.0")
        code, out = self.run_setup("doctor")
        self.assertEqual(code, 1, out)
        row = next(l for l in out.splitlines() if l.strip().startswith("git"))
        self.assertIn("нет", row)
        self.assertIn("git", row.split("нет", 1)[1])          # как поставить — в той же строке
        for tid in IDS:
            self.assertIn(tid, out)

    def test_json_has_six_positions_with_versions(self):
        self.fake("node", "v20.11.0")
        self.fake("git", "git version 2.44.1")
        self.fake("ffmpeg", "ffmpeg version 7.1 Copyright (c) 2000-2024")
        os.makedirs(os.path.join(self.browsers, "chromium-1243"))
        code, out = self.run_setup("doctor", "--need", "video,check", "--json")
        rows = json.loads(out)
        self.assertEqual([r["id"] for r in rows], IDS)
        by = {r["id"]: r for r in rows}
        self.assertEqual(code, 0, out)
        self.assertEqual(by["git"]["version"], "2.44.1")
        self.assertEqual(by["node"]["version"], "20.11.0")
        self.assertEqual(by["ffmpeg"]["version"], "7.1")
        self.assertTrue(by["playwright"]["present"])
        self.assertTrue(by["python"]["present"])           # скрипт сам идёт под Python
        self.assertIsNone(by["figma"]["present"])          # подключение MCP видит только агент

    def test_requested_need_turns_missing_into_code_1(self):
        self.fake("node", "v20.11.0")
        self.fake("git", "git version 2.44.1")
        self.assertEqual(self.run_setup("doctor")[0], 0)
        code, out = self.run_setup("doctor", "--need", "video")
        self.assertEqual(code, 1, out)
        self.assertIn("ffmpeg", out)

    def test_old_node_needs_an_update_with_a_link_to_nodejs_org(self):
        """Playwright и nodejs.org: поддерживаются только линии LTS от 22; старее — обновить."""
        self.fake("git", "git version 2.44.1")
        self.fake("node", "v18.20.4")
        code, out = self.run_setup("doctor", "--need", "build", "--json")
        node = {r["id"]: r for r in json.loads(out)}["node"]
        self.assertEqual(code, 1, out)
        self.assertFalse(node["present"])
        self.assertEqual(node["version"], "18.20.4")
        self.assertIn("нужно обновить", node["hint"])
        self.assertIn("https://nodejs.org", node["hint"])
        code, out = self.run_setup("doctor", "--need", "build")
        row = next(l for l in out.splitlines() if l.strip().startswith("node"))
        self.assertIn("нужно обновить", row)
        self.fake("node", "v22.11.0")
        code, out = self.run_setup("doctor", "--need", "build", "--json")
        self.assertEqual(code, 0, out)
        self.assertTrue({r["id"]: r for r in json.loads(out)}["node"]["present"])

    def test_mac_without_homebrew_starts_with_homebrew_for_the_human(self):
        self.fake("node", "v22.11.0")                          # git нет, brew нет
        code, out = self.run_setup("doctor", "--os", "mac")
        self.assertEqual(code, 1, out)
        first = out.splitlines()[0]
        self.assertIn("выполните в своём Терминале", first)
        self.assertIn("Homebrew/install", first)


class Plan(Base):
    ALL = ["python", "git", "node", "playwright", "ffmpeg"]

    def cmds(self, steps, tid):
        return [s["cmd"] for s in steps if s["id"] == tid]

    def test_mac_uses_homebrew_without_admin(self):
        steps = self.plan(*self.ALL, "--os", "mac")
        self.assertIn(["brew", "install", "git"], self.cmds(steps, "git"))
        self.assertIn(["brew", "install", "node"], self.cmds(steps, "node"))
        self.assertIn(["brew", "install", "ffmpeg"], self.cmds(steps, "ffmpeg"))
        self.assertIn(["npx", "playwright", "install", "chromium"], self.cmds(steps, "playwright"))
        self.assertFalse(any(s["needs_admin"] for s in steps))

    def test_windows_uses_winget_and_marks_admin_installers(self):
        steps = self.plan(*self.ALL, "--os", "windows")
        git = next(s for s in steps if s["id"] == "git")
        self.assertEqual(git["cmd"][:2], ["winget", "install"])
        self.assertIn("Git.Git", git["cmd"])
        self.assertTrue(git["needs_admin"])
        self.assertIn("OpenJS.NodeJS.LTS", self.cmds(steps, "node")[0])
        self.assertIn("Python.Python.3.12", self.cmds(steps, "python")[0])
        self.assertIn("Gyan.FFmpeg", self.cmds(steps, "ffmpeg")[0])
        self.assertIn(["npx", "playwright", "install", "chromium"], self.cmds(steps, "playwright"))

    def test_winget_accepts_agreements_so_it_never_waits_for_a_keypress(self):
        """learn.microsoft.com: без этих флагов winget спрашивает согласие и ждёт ввода."""
        steps = self.plan(*self.ALL, "--os", "windows")
        winget = [s["cmd"] for s in steps if s["cmd"][:1] == ["winget"]]
        self.assertEqual(len(winget), 4, winget)
        for cmd in winget:
            self.assertIn("--accept-source-agreements", cmd)
            self.assertIn("--accept-package-agreements", cmd)

    def test_linux_package_managers_need_sudo_and_are_marked(self):
        for pkg, word in (("apt", "apt-get"), ("dnf", "dnf"), ("pacman", "pacman")):
            steps = self.plan(*self.ALL, "--os", "linux", "--pkg", pkg)
            git = self.cmds(steps, "git")[0]
            self.assertEqual(git[:2], ["sudo", word], pkg)
            for s in steps:
                if s["cmd"] and s["cmd"][0] == "sudo":
                    self.assertTrue(s["needs_admin"], s)
            pw = self.cmds(steps, "playwright")
            self.assertIn(["npx", "playwright", "install", "chromium"], pw)
            self.assertTrue(any("install-deps" in c for c in pw), pw)
        self.assertEqual(self.cmds(self.plan("git", "--os", "linux"), "git")[0][:2], ["sudo", "apt-get"])

    def test_figma_gives_connect_commands_per_host(self):
        claude = self.cmds(self.plan("figma", "--os", "mac", "--host", "claude"), "figma")
        self.assertIn(["claude", "mcp", "add", "--transport", "http", "figma", "https://mcp.figma.com/mcp"], claude)
        codex = self.cmds(self.plan("figma", "--os", "mac", "--host", "codex"), "figma")
        self.assertIn(["codex", "mcp", "add", "figma", "--url", "https://mcp.figma.com/mcp"], codex)
        self.assertIn(["codex", "mcp", "login", "figma"], codex)

    def test_webp_tools_come_from_each_package_manager(self):
        """cwebp — запасной путь WebP для media.py prep, когда в ffmpeg нет libwebp."""
        self.assertEqual(self.cmds(self.plan("webp", "--os", "mac"), "webp"), [["brew", "install", "webp"]])
        self.assertIn("Google.Libwebp", self.cmds(self.plan("webp", "--os", "windows"), "webp")[0])
        for pkg, name in (("apt", "webp"), ("dnf", "libwebp-tools"), ("pacman", "libwebp")):
            cmd = self.cmds(self.plan("webp", "--os", "linux", "--pkg", pkg), "webp")[0]
            self.assertEqual((cmd[0], cmd[-1]), ("sudo", name), pkg)

    def test_unknown_tool_or_os_is_an_input_error(self):
        self.assertEqual(self.run_setup("plan", "photoshop", "--os", "mac")[0], 2)
        self.assertEqual(self.run_setup("plan", "git", "--os", "beos")[0], 2)


@unittest.skipUnless(UNIX, "поддельные программы — shell-скрипты")
class Install(Base):
    def test_without_yes_only_plan(self):
        self.fake("brew")
        code, out = self.run_install("git", "--os", "mac", "--pkg", "brew")
        self.assertIn("brew install git", out)
        self.assertEqual(self.called(), "")

    def test_runs_steps_one_by_one(self):
        self.fake("brew", "готово")
        code, out = self.run_install("git", "ffmpeg", "--yes", "--os", "mac", "--pkg", "brew")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.called().splitlines(), ["brew install git", "brew install ffmpeg"])
        self.assertIn("brew install git", out)

    def test_admin_steps_go_to_the_human(self):
        self.fake("sudo")
        code, out = self.run_install("git", "--yes", "--os", "linux", "--pkg", "apt")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.called(), "")
        self.assertIn("выполните в своём Терминале: sudo apt-get install -y git", out)

    def test_failure_shows_code_and_tail_and_stops(self):
        self.fake("brew", "Error: сеть недоступна", code=3)
        code, out = self.run_install("git", "ffmpeg", "--yes", "--os", "mac", "--pkg", "brew")
        self.assertEqual(code, 1, out)
        self.assertIn("3", out)
        self.assertIn("сеть недоступна", out)
        self.assertEqual(self.called().splitlines(), ["brew install git"])

    def test_mac_without_homebrew_first_line_is_homebrew_for_the_human(self):
        self.fake("git", "git version 2.44.1")                 # brew нет
        code, out = self.run_install("git", "ffmpeg", "--yes", "--os", "mac")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.called(), "")
        first = out.splitlines()[0]
        self.assertTrue(first.startswith("выполните в своём Терминале: "), out)
        self.assertIn("Homebrew/install", first)
        self.assertIn("install ffmpeg git --yes", out)          # что поставить после «готово»

    def test_a_hanging_step_is_stopped_by_the_time_limit(self):
        write(os.path.join(self.bin, "brew"), "#!/bin/sh\necho \"brew $*\" >> \"%s\"\n/bin/sleep 20\n" % self.calls, exe=True)
        code, out = self.run_install("git", "ffmpeg", "--yes", "--os", "mac", "--pkg", "brew",
                                     AIDESIGN_SETUP_TIMEOUT="1")
        self.assertEqual(code, 1, out)
        self.assertIn("не уложилась", out)
        self.assertEqual(self.called().splitlines(), ["brew install git"])

    def test_substitute_path_is_refused_by_install(self):
        """AIDESIGN_SETUP_PATH — только для проб: install с ней не ставит ничего."""
        self.fake("brew", "готово")
        code, out = self.run_setup("install", "git", "--yes", "--os", "mac", "--pkg", "brew")
        self.assertEqual(code, 2, out)
        self.assertIn("AIDESIGN_SETUP_PATH", out)
        self.assertEqual(self.called(), "")
        self.assertEqual(self.run_setup("plan", "git", "--os", "mac")[0], 0)


if __name__ == "__main__":
    unittest.main()
