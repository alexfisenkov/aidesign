"""Тесты skills/aidesign/tools/backup.py — бэкапов и отката.

Всё — во временных папках: create → правка → restore → суммы совпадают,
лишний файл унесён, ничего не удалено. Шов — командная строка.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools", "backup.py")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tree(root, skip=(".aidesign-work",)):
    out = {}
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = sha(p)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="backup-test-")
        write(os.path.join(self.root, "index.html"), "<!doctype html><title>сайт</title>")
        write(os.path.join(self.root, "assets", "css", "site.css"), "body{margin:0}")
        write(os.path.join(self.root, "страницы", "о нас.html"), "<p>о нас</p>")
        write(os.path.join(self.root, "node_modules", "lib", "index.js"), "x")
        write(os.path.join(self.root, ".git", "HEAD"), "ref: refs/heads/main")
        write(os.path.join(self.root, ".aidesign-work", "state.js"), "window.STATE = {}")
        write(os.path.join(self.root, "dist", "app.js"), "built")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def bk(self, *args):
        r = subprocess.run([sys.executable, "-B", BACKUP] + list(args) + ["--root", self.root],
                           capture_output=True, text=True, encoding="utf-8", cwd=self.root, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def create(self, reason="до", *extra):
        code, out = self.bk("create", "--reason", reason, "--json", *extra)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def manifest(self, bid):
        with open(os.path.join(self.root, ".aidesign-work", "backups", bid, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)


class Create(Base):
    def test_copy_with_manifest_and_sums(self):
        b = self.create("до правок")
        self.assertRegex(b["id"], r"^\d{8}-\d{6}-до-правок$")
        m = self.manifest(b["id"])
        paths = {f["path"] for f in m["files"]}
        self.assertEqual(paths, {"index.html", "assets/css/site.css", "страницы/о нас.html", "dist/app.js",
                                 ".gitignore"})                         # под git дописан до копии
        for f in m["files"]:
            copy = os.path.join(self.root, ".aidesign-work", "backups", b["id"], "files", f["path"])
            self.assertEqual(sha(copy), f["sha256"])
            self.assertEqual(sha(os.path.join(self.root, f["path"])), f["sha256"])
            self.assertEqual(os.path.getsize(copy), f["size"])
        self.assertEqual(m["bytes"], sum(f["size"] for f in m["files"]))
        self.assertEqual((m["id"], m["reason"]), (b["id"], "до правок"))
        for key in ("createdAt", "root", "excluded"):
            self.assertIn(key, m)
        self.assertIn("node_modules", " ".join(m["excluded"]))

    def test_dist_is_excluded_only_when_project_builds_it(self):
        write(os.path.join(self.root, "package.json"), json.dumps({"scripts": {"build": "vite build"}}))
        paths = {f["path"] for f in self.manifest(self.create()["id"])["files"]}
        self.assertNotIn("dist/app.js", paths)
        self.assertIn("package.json", paths)

    def test_over_limit_needs_force(self):
        write(os.path.join(self.root, "big.bin"), "x" * 300000)
        code, out = self.bk("create", "--reason", "до", "--limit-mb", "0.1")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"\d")
        self.assertFalse(os.path.isdir(os.path.join(self.root, ".aidesign-work", "backups")) and
                         os.listdir(os.path.join(self.root, ".aidesign-work", "backups")))
        code, out = self.bk("create", "--reason", "до", "--limit-mb", "0.1", "--force")
        self.assertEqual(code, 0, out)

    def test_project_without_regular_files_gives_an_empty_copy(self):
        empty = tempfile.mkdtemp(prefix="backup-empty-")
        self.addCleanup(shutil.rmtree, empty, True)
        r = subprocess.run([sys.executable, "-B", BACKUP, "create", "--reason", "до", "--json", "--root", empty],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        bid = json.loads(r.stdout)["id"]
        with open(os.path.join(empty, ".aidesign-work", "backups", bid, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["files"], [])

    def test_under_git_the_work_folder_goes_to_gitignore_before_the_copy(self):
        write(os.path.join(self.root, ".gitignore"), "secret.txt")              # без перевода строки в конце
        self.create()
        self.create()
        gi = read(os.path.join(self.root, ".gitignore"))
        self.assertTrue(gi.startswith("secret.txt\n"), gi)
        self.assertEqual(gi.splitlines().count(".aidesign-work/"), 1, gi)

    def test_without_git_gitignore_is_not_created(self):
        shutil.rmtree(os.path.join(self.root, ".git"))
        self.create()
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitignore")))

    @unittest.skipUnless(shutil.which("git"), "git не установлен")
    def test_copy_does_not_get_into_the_commit_before_the_redesign(self):
        shutil.rmtree(os.path.join(self.root, ".git"))
        subprocess.run(["git", "init", "-q", self.root], check=True, capture_output=True)
        self.create()
        subprocess.run(["git", "-C", self.root, "add", "-A"], check=True, capture_output=True)
        staged = subprocess.run(["git", "-C", self.root, "diff", "--cached", "--name-only"],
                                capture_output=True, text=True, encoding="utf-8").stdout
        self.assertIn(".gitignore", staged)
        self.assertNotIn(".aidesign-work", staged)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "ссылки — на Unix")
    def test_work_folder_as_a_link_is_refused(self):
        outside = tempfile.mkdtemp(prefix="backup-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        shutil.rmtree(os.path.join(self.root, ".aidesign-work"))
        os.symlink(outside, os.path.join(self.root, ".aidesign-work"))
        code, out = self.bk("create", "--reason", "до")
        self.assertEqual(code, 1, out)
        self.assertIn("ссылка", out)
        self.assertEqual(os.listdir(outside), [])

    def test_list_and_verify(self):
        b = self.create()
        code, out = self.bk("list", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual([x["id"] for x in json.loads(out)], [b["id"]])
        self.assertEqual(self.bk("verify", "--id", b["id"])[0], 0)
        copy = os.path.join(self.root, ".aidesign-work", "backups", b["id"], "files", "index.html")
        write(copy, "испорчено")
        code, out = self.bk("verify", "--id", b["id"])
        self.assertEqual(code, 1, out)
        self.assertIn("index.html", out)


class Restore(Base):
    def change(self):
        write(os.path.join(self.root, "index.html"), "<!doctype html><title>новый</title>")
        os.remove(os.path.join(self.root, "assets", "css", "site.css"))
        write(os.path.join(self.root, "assets", "css", "новый.css"), "a{}")

    def test_without_yes_only_a_plan(self):
        b = self.create()
        self.change()
        before = tree(self.root)
        code, out = self.bk("restore", "--id", b["id"])
        self.assertEqual(code, 0, out)
        self.assertIn("новый.css", out)
        self.assertEqual(tree(self.root), before)

    def test_restore_brings_files_back_and_moves_extra(self):
        b = self.create()
        original = tree(self.root, skip=(".aidesign-work", "node_modules", ".git"))
        self.change()
        changed = tree(self.root, skip=(".aidesign-work", "node_modules", ".git"))
        code, out = self.bk("restore", "--id", b["id"], "--yes", "--json")
        self.assertEqual(code, 0, out)
        res = json.loads(out)
        self.assertEqual(tree(self.root, skip=(".aidesign-work", "node_modules", ".git")), original)
        self.assertEqual(res["moved_extra"], ["assets/css/новый.css"])
        extra = os.path.join(self.root, ".aidesign-work", "backups", b["id"] + "-лишнее", "assets", "css", "новый.css")
        self.assertEqual(sha(extra), changed["assets/css/новый.css"])
        pre = self.manifest(res["pre_backup_id"])                       # копия «перед откатом»
        self.assertEqual({f["path"]: f["sha256"] for f in pre["files"]}, changed)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "node_modules", "lib", "index.js")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, ".git", "HEAD")))

    def test_empty_folders_made_after_the_copy_are_moved_aside(self):
        os.makedirs(os.path.join(self.root, "пустая-до"))                  # была пустой и в копии
        b = self.create()
        os.makedirs(os.path.join(self.root, "новая", "вложенная"))        # пустая, появилась после копии
        write(os.path.join(self.root, "раздел", "page.html"), "<p>новое</p>")   # папка опустеет после выноса файла
        os.makedirs(os.path.join(self.root, "assets", "img"))               # пустая внутри папки из копии
        code, out = self.bk("restore", "--id", b["id"])
        self.assertEqual(code, 0, out)
        self.assertIn("новая/", out)                                        # план называет и папки
        code, out = self.bk("restore", "--id", b["id"], "--yes", "--json")
        self.assertEqual(code, 0, out)
        res = json.loads(out)
        extra = os.path.join(self.root, ".aidesign-work", "backups", b["id"] + "-лишнее")
        for rel in ("новая", "раздел", "assets/img"):
            self.assertFalse(os.path.exists(os.path.join(self.root, rel)), rel)
            self.assertTrue(os.path.isdir(os.path.join(extra, rel)), rel)
            self.assertIn(rel + "/", res["moved_extra"])
        self.assertTrue(os.path.isdir(os.path.join(extra, "новая", "вложенная")))
        self.assertTrue(os.path.isfile(os.path.join(extra, "раздел", "page.html")))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "пустая-до")))   # была в копии — остаётся
        self.assertTrue(os.path.isdir(os.path.join(self.root, "assets", "css")))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "node_modules")))

    def test_restore_from_broken_copy_is_refused(self):
        b = self.create()
        os.remove(os.path.join(self.root, ".aidesign-work", "backups", b["id"], "files", "index.html"))
        self.change()
        before = tree(self.root)
        code, out = self.bk("restore", "--id", b["id"], "--yes")
        self.assertEqual(code, 1, out)
        self.assertEqual(tree(self.root), before)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "ссылки — на Unix")
    def test_links_on_the_way_are_moved_aside_not_written_through(self):
        """Ссылка на месте файла или папки по пути не используется для записи: чужое цело."""
        outside = tempfile.mkdtemp(prefix="backup-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        write(os.path.join(outside, "secret.txt"), "чужое")
        write(os.path.join(self.root, "a.txt"), "мой a")
        write(os.path.join(self.root, "sub", "b.txt"), "мой b")
        b = self.create()
        os.remove(os.path.join(self.root, "a.txt"))
        os.symlink(os.path.join(outside, "secret.txt"), os.path.join(self.root, "a.txt"))
        shutil.rmtree(os.path.join(self.root, "sub"))
        os.symlink(outside, os.path.join(self.root, "sub"))
        code, out = self.bk("restore", "--id", b["id"], "--yes", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(os.listdir(outside), ["secret.txt"])
        with open(os.path.join(outside, "secret.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "чужое")
        for rel, text in (("a.txt", "мой a"), ("sub/b.txt", "мой b")):
            p = os.path.join(self.root, *rel.split("/"))
            self.assertFalse(os.path.islink(p) or os.path.islink(os.path.dirname(p)), rel)
            with open(p, encoding="utf-8") as f:
                self.assertEqual(f.read(), text)
        extra = os.path.join(self.root, ".aidesign-work", "backups", b["id"] + "-лишнее")
        self.assertTrue(os.path.islink(os.path.join(extra, "a.txt")))       # ссылка сохранена как ссылка
        self.assertTrue(os.path.islink(os.path.join(extra, "sub")))
        self.assertTrue({"a.txt", "sub"} <= set(json.loads(out)["moved_extra"]))

    def test_unknown_id_is_an_input_error(self):
        self.assertEqual(self.bk("restore", "--id", "нет-такого", "--yes")[0], 2)
        self.assertEqual(self.bk("restore", "--id", "..", "--yes")[0], 2)

    def test_manifest_with_paths_out_of_the_project_is_refused_before_anything(self):
        """«..» и абсолютные пути в описи — отказ до копии «перед откатом» и до любой записи."""
        outside = tempfile.mkdtemp(prefix="backup-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        b = self.create()
        mpath = os.path.join(self.root, ".aidesign-work", "backups", b["id"], "manifest.json")
        good = self.manifest(b["id"])
        target = os.path.join(outside, "x.txt")
        for bad in ("../x.txt", "assets/../../x.txt", target, "/etc/hosts", "C:/x.txt", "a\\..\\..\\x.txt"):
            m = dict(good, files=good["files"] + [{"path": bad, "size": 1, "sha256": "0" * 64}])
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(m, f)
            before = sorted(os.listdir(os.path.join(self.root, ".aidesign-work", "backups")))
            for args in (("restore", "--id", b["id"], "--yes"), ("restore", "--id", b["id"]), ("verify", "--id", b["id"])):
                code, out = self.bk(*args)
                self.assertNotEqual(code, 0, (bad, args, out))
                self.assertIn("за пределы проекта", out, (bad, args))
            self.assertEqual(sorted(os.listdir(os.path.join(self.root, ".aidesign-work", "backups"))), before, bad)
            self.assertEqual(os.listdir(outside), [], bad)


if __name__ == "__main__":
    unittest.main()
