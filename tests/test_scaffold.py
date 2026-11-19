"""Тесты skills/aidesign/tools/scaffold.py — структуры проекта.

Во временной папке: пустая получает схему целиком, непустая — ничего не теряет
и не перезаписывается, `.gitignore` дописывается, `--git` делает первый коммит.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCAFFOLD = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools", "scaffold.py")
COMMON = ["index.html", "assets/css", "assets/js", "assets/img", "assets/video", "assets/fonts",
          "design-system", "DESIGN.md", "AGENTS.md", "CLAUDE.md", "README.md", ".gitignore"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="scaffold-test-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def sc(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        r = subprocess.run([sys.executable, "-B", SCAFFOLD] + list(args) + ["--root", self.root],
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def plan(self, kind):
        code, out = self.sc("plan", "--kind", kind, "--json")
        self.assertEqual(code, 0, out)
        return {i["path"]: i for i in json.loads(out)}


class Empty(Base):
    def test_plan_in_empty_folder_creates_everything(self):
        page = self.plan("page")
        self.assertEqual(set(page), set(COMMON))
        self.assertEqual({i["action"] for i in page.values()}, {"create"})
        site = self.plan("site")
        self.assertEqual(set(site), set(COMMON) | {"pages"})
        self.assertEqual(os.listdir(self.root), [])                 # plan ничего не пишет

    def test_apply_creates_schema(self):
        code, out = self.sc("apply", "--kind", "site", "--title", "Студия глины")
        self.assertEqual(code, 0, out)
        for rel in COMMON + ["pages"]:
            self.assertTrue(os.path.exists(os.path.join(self.root, rel)), rel)
        self.assertEqual(read(os.path.join(self.root, "CLAUDE.md")).strip(), "@AGENTS.md")
        agents = read(os.path.join(self.root, "AGENTS.md"))
        self.assertIn("<!-- aidesign:start -->", agents)
        self.assertIn("<!-- aidesign:end -->", agents)
        self.assertIn(".aidesign-work/", read(os.path.join(self.root, ".gitignore")))
        self.assertIn("Студия глины", read(os.path.join(self.root, "index.html")))
        self.assertEqual({i["action"] for i in self.plan("site").values()}, {"skip"})


class Existing(Base):
    def setUp(self):
        super().setUp()
        write(os.path.join(self.root, "index.html"), "<!doctype html><title>мой сайт</title>")
        write(os.path.join(self.root, "style.css"), "body{}")
        write(os.path.join(self.root, "README.md"), "# мой\n")
        write(os.path.join(self.root, ".gitignore"), "secret.txt\n")
        write(os.path.join(self.root, "AGENTS.md"), "# Мои правила\n")

    def test_nothing_is_overwritten_and_gitignore_is_appended(self):
        before = {p: read(os.path.join(self.root, p)) for p in ("index.html", "style.css", "README.md", "AGENTS.md")}
        plan = self.plan("page")
        self.assertEqual(plan["index.html"]["action"], "skip")
        self.assertEqual(plan["assets/css"]["action"], "propose")      # раскладку готового сайта — только с согласия
        self.assertEqual(plan[".gitignore"]["action"], "append")
        code, out = self.sc("apply", "--kind", "page", "--title", "Мой")
        self.assertEqual(code, 0, out)
        for p, text in before.items():
            self.assertEqual(read(os.path.join(self.root, p)), text, p)
        gi = read(os.path.join(self.root, ".gitignore"))
        self.assertTrue(gi.startswith("secret.txt\n"))
        self.assertIn(".aidesign-work/", gi)
        self.assertFalse(os.path.exists(os.path.join(self.root, "assets")))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "design-system")))
        self.assertEqual(read(os.path.join(self.root, "CLAUDE.md")).strip(), "@AGENTS.md")
        code, out = self.sc("apply", "--kind", "page", "--title", "Мой")      # второй раз — без дублей
        self.assertEqual(read(os.path.join(self.root, ".gitignore")).count(".aidesign-work/"), 1)


class Memory(Base):
    def test_own_claude_md_alone_gets_no_agents_md(self):
        """Один свой CLAUDE.md — блок aidesign пойдёт в него; рядом AGENTS.md не заводится."""
        write(os.path.join(self.root, "CLAUDE.md"), "# Мой проект\n\nПиши коротко.\n")
        plan = self.plan("page")
        self.assertNotEqual(plan["AGENTS.md"]["action"], "create")
        self.assertIn("CLAUDE.md", plan["AGENTS.md"]["note"])
        code, out = self.sc("apply", "--kind", "page", "--title", "Мой")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "AGENTS.md")))
        self.assertEqual(read(os.path.join(self.root, "CLAUDE.md")), "# Мой проект\n\nПиши коротко.\n")

    def test_claude_md_that_only_imports_agents_md_still_gets_agents_md(self):
        write(os.path.join(self.root, "CLAUDE.md"), "@AGENTS.md\n")
        self.assertEqual(self.plan("page")["AGENTS.md"]["action"], "create")
        self.assertEqual(self.sc("apply", "--kind", "page", "--title", "Мой")[0], 0)
        self.assertIn("<!-- aidesign:start -->", read(os.path.join(self.root, "AGENTS.md")))


@unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "ссылки — на Unix")
class Links(Base):
    def test_gitignore_link_is_not_opened_for_writing(self):
        outside = tempfile.mkdtemp(prefix="scaffold-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        target = os.path.join(outside, "global-ignore")
        write(target, "*.log\n")
        os.symlink(target, os.path.join(self.root, ".gitignore"))
        code, out = self.sc("apply", "--kind", "page", "--title", "Мой")
        self.assertEqual(read(target), "*.log\n")
        self.assertIn(".gitignore", out)
        self.assertIn("ссылка", out)
        self.assertTrue(os.path.islink(os.path.join(self.root, ".gitignore")))


@unittest.skipUnless(shutil.which("git"), "git не установлен")
class Git(Base):
    def test_git_init_and_commit_before_ai_design(self):
        write(os.path.join(self.root, "index.html"), "<!doctype html><title>мой сайт</title>")
        code, out = self.sc("apply", "--kind", "page", "--title", "Мой", "--git")
        self.assertEqual(code, 0, out)
        log = subprocess.run(["git", "-C", self.root, "log", "--format=%s"], capture_output=True, text=True).stdout
        self.assertEqual(log.strip().splitlines()[-1], "До AI Design")
        first = subprocess.run(["git", "-C", self.root, "show", "--name-only", "--format=", "HEAD~0" if
                                len(log.strip().splitlines()) == 1 else "HEAD~1"],
                               capture_output=True, text=True).stdout.split()
        self.assertEqual(first, [".gitignore", "index.html"])          # коммит — до раскладки

    def test_secrets_and_dependencies_stay_out_of_the_first_commit(self):
        write(os.path.join(self.root, "index.html"), "<!doctype html><title>мой сайт</title>")
        write(os.path.join(self.root, ".env"), "TOKEN=x\n")
        write(os.path.join(self.root, ".env.local"), "TOKEN=y\n")
        write(os.path.join(self.root, ".env.example"), "TOKEN=\n")
        write(os.path.join(self.root, "node_modules", "lib", "index.js"), "x")
        code, out = self.sc("apply", "--kind", "page", "--title", "Мой", "--git")
        self.assertEqual(code, 0, out)
        files = subprocess.run(["git", "-C", self.root, "ls-files"], capture_output=True, text=True).stdout.split()
        self.assertNotIn(".env", files)
        self.assertNotIn(".env.local", files)
        self.assertFalse(any(f.startswith("node_modules/") for f in files), files)
        self.assertIn(".env.example", files)
        self.assertIn(".gitignore", files)


if __name__ == "__main__":
    unittest.main()
