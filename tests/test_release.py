"""Выпускные проверки AI Design: версии, чистота дерева, README, ручной CI.

Запуск из корня репозитория:  python3 -B -m unittest tests.test_release
Швы — чтение файлов репозитория:
- `metadata.version` в SKILL.md равна верхней записи CHANGELOG.md;
- в дереве нет путей Мака, адресов почты и токенов по образцам;
- слова об основе семейства есть только в LICENSE и в последней строке README;
- README.md и README.ru.md зеркальны и называют каждый источник из THIRD_PARTY_NOTICES.md;
- ci.yml запускается только вручную и на трёх системах;
- tools/public-export.py собирает чистую выгрузку и ловит запретное;
- THIRD_PARTY_NOTICES.md называет те же файлы, что шапки knowledge/движение-и-медиа/.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILL_MD = os.path.join(REPO, "skills", "aidesign", "SKILL.md")
SKIP_DIRS = {".git", ".sources", ".aispa-work", ".aidesign-work", "__pycache__", "node_modules"}
SKIP_FILES = {"БРИФ.md"}
READMES = ("README.md", "README.ru.md")

MAC_PATH = "/Use" + "rs/"                      # собрано по частям, чтобы тест не находил сам себя
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
HARMLESS_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
SECRETS = [
    ("ключ sk-", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("токен GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("ключ AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("ключ Google", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("токен Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("токен Telegram", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("закрытый ключ", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]
BASE_WORDS = re.compile("auto" + "pilot|nick" + r"\s+vels", re.I)   # тоже по частям
EXPORT = os.path.join(REPO, "tools", "public-export.py")
MOTION = os.path.join(REPO, "skills", "aidesign", "knowledge", "движение-и-медиа")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def tree_files():
    """Текстовые файлы дерева вместе с tests/: (относительный путь, текст)."""
    found = []
    for base, dirs, names in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name in SKIP_FILES or name == ".DS_Store":
                continue
            path = os.path.join(base, name)
            try:
                text = read(path)
            except (UnicodeDecodeError, OSError):
                continue                           # картинки и прочее бинарное
            found.append((os.path.relpath(path, REPO), text))
    return found


def skill_version():
    m = re.search(r'^\s*version:\s*"([^"]+)"', read(SKILL_MD), re.M)
    return m.group(1) if m else None


def changelog_top():
    m = re.search(r"^## (\d+\.\d+\.\d+)", read(os.path.join(REPO, "CHANGELOG.md")), re.M)
    return m.group(1) if m else None


class Versions(unittest.TestCase):

    def test_skill_version_equals_top_of_the_changelog(self):
        self.assertIsNotNone(skill_version())
        self.assertEqual(skill_version(), changelog_top())

    def test_the_first_release_is_zero_one_zero(self):
        self.assertIn("## 0.1.0", read(os.path.join(REPO, "CHANGELOG.md")))

    def test_the_iteration_of_19_11_is_version_zero_two_zero(self):
        self.assertIn("## 0.2.0", read(os.path.join(REPO, "CHANGELOG.md")))

    def test_the_media_iteration_is_version_zero_three_zero(self):
        self.assertEqual(skill_version(), "0.3.0")
        self.assertEqual(changelog_top(), "0.3.0")

    def test_the_zero_three_zero_entry_tells_what_is_new_in_plain_words(self):
        text = read(os.path.join(REPO, "CHANGELOG.md"))
        entry = re.search(r"^## 0\.3\.0[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        self.assertIsNotNone(entry, "нет записи 0.3.0")
        body = entry.group(1)
        for word in ("генератор", "бюджет", "media.py", "assets/media.json", "настоящ", "file://",
                     "снимк", "Открыть в новой вкладке", "доводит"):
            self.assertIn(word, body, word)


class CleanTree(unittest.TestCase):

    def test_no_mac_paths_in_the_tree(self):
        for rel, text in tree_files():
            self.assertNotIn(MAC_PATH, text, rel)

    def test_no_email_addresses_in_the_tree(self):
        for rel, text in tree_files():
            for address in EMAIL.findall(text):
                domain = address.rsplit("@", 1)[1].lower()
                self.assertIn(domain, HARMLESS_EMAIL_DOMAINS, "%s: %s" % (rel, address))

    def test_no_tokens_by_known_patterns(self):
        for rel, text in tree_files():
            for label, pattern in SECRETS:
                self.assertIsNone(pattern.search(text), "%s: похоже на %s" % (rel, label))

    def test_no_env_files_are_committed(self):
        for base, dirs, names in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
                    self.fail("файл окружения в дереве: %s" % os.path.join(base, name))

    def test_base_skill_words_live_only_in_license_and_last_line_of_readme(self):
        for rel, text in tree_files():
            if rel == "LICENSE":
                continue
            if rel in READMES:
                body = text.rstrip().splitlines()
                self.assertFalse(BASE_WORDS.search("\n".join(body[:-1])), "%s: не в последней строке" % rel)
                continue
            self.assertFalse(BASE_WORDS.search(text), rel)

    def test_license_and_the_last_line_of_both_readmes_credit_the_base(self):
        self.assertRegex(read(os.path.join(REPO, "LICENSE")), r"(?i)nick\s+vels")
        for name in READMES:
            last = read(os.path.join(REPO, name)).rstrip().splitlines()[-1]
            self.assertIn("[MIT](LICENSE) © Alexander Fisenkov", last, name)
            self.assertRegex(last, r"(?i)nick\s+vels", name)


class Readmes(unittest.TestCase):

    def headings(self, name, level="## "):
        return [l for l in read(os.path.join(REPO, name)).splitlines() if l.startswith(level)]

    def test_both_readmes_have_the_same_number_of_sections(self):
        self.assertEqual(len(self.headings("README.md")), len(self.headings("README.ru.md")))
        self.assertEqual(len(self.headings("README.md", "### ")), len(self.headings("README.ru.md", "### ")))

    def test_both_readmes_carry_the_install_command(self):
        command = "npx skills add alexfisenkov/aidesign --skill aidesign -g -y -a claude-code codex"
        for name in READMES:
            self.assertIn(command, read(os.path.join(REPO, name)), name)
            self.assertIn("npx skills update aidesign -g", read(os.path.join(REPO, name)), name)

    def test_both_readmes_use_the_same_images_and_they_exist(self):
        found = []
        for name in READMES:
            images = re.findall(r'<img src="([^"]+)"', read(os.path.join(REPO, name)))
            self.assertGreaterEqual(len(images), 3, name)
            for image in images:
                self.assertTrue(os.path.isfile(os.path.join(REPO, image)), "%s: нет %s" % (name, image))
            found.append(sorted(i for i in images if "panel" not in i))
        self.assertEqual(found[0], found[1])

    def test_both_readmes_name_every_source_address_from_third_party_notices(self):
        notices = read(os.path.join(REPO, "THIRD_PARTY_NOTICES.md"))
        urls = []
        for line in notices.splitlines():
            if line.startswith("- **Адрес:**") or line.startswith("- **Условия:**"):
                urls += re.findall(r"https?://[^\s)`,;]+", line)
        self.assertGreaterEqual(len(urls), 18)
        for name in READMES:
            text = read(os.path.join(REPO, name))
            for url in urls:
                self.assertIn(url, text, "%s: нет источника %s" % (name, url))

    def test_both_readmes_name_the_family_in_one_line_with_links(self):
        links = ("https://github.com/alexfisenkov/aispa", "https://github.com/alexfisenkov/aimaster",
                 "https://github.com/alexfisenkov/AIEditing")
        for name in READMES:
            lines = [l for l in read(os.path.join(REPO, name)).splitlines() if all(u + ")" in l for u in links)]
            self.assertEqual(len(lines), 1, "%s: соседи семейства одной строкой" % name)

    def test_both_readmes_carry_the_sections_of_iteration_19(self):
        must = (
            "brew install node", "winget install OpenJS.NodeJS.LTS", "https://nodejs.org",   # с нуля, три ОС
            "releases", ".claude/skills/aidesign", ".agents/skills/aidesign",               # запасной путь
            "backup.py restore", ".aidesign-work/backups/",                                 # бэкапы и откат
            "design-system/", "tokens.css", "tokens.json", "styleguide.html",               # дизайн-система
            "https://mcp.figma.com/mcp", "codex mcp login figma",                           # Figma
            "Playwright",                                                                   # оснащение агента
        )
        for name in READMES:
            text = read(os.path.join(REPO, name))
            for word in must:
                self.assertIn(word, text, "%s: нет «%s»" % (name, word))
            self.assertNotRegex(text, r"\$\s?\d|\d\s?(?:\$|USD|₽|руб)", "%s: цены в README не пишутся" % name)

    def test_both_readmes_explain_media_budget_real_previews_and_http(self):
        words = {
            "README.ru.md": ("бюджет", "потрачено", "настоящ", "довод", "не как файл", "свои"),
            "README.md": ("budget", "spent", "real", "polish", "not as a file", "your own"),
        }
        for name in READMES:
            text = read(os.path.join(REPO, name))
            for word in words[name] + ("http://localhost", "`tools/media.py`", "`tools/shots.py`",
                                       "`tools/rules.py`"):
                self.assertIn(word, text, "%s: нет «%s»" % (name, word))

    def test_both_readmes_describe_the_two_orders_with_aispa_and_both_entries(self):
        for name in READMES:
            text = read(os.path.join(REPO, name))
            self.assertIn("1.0.3", text, name)
            self.assertIn("aidesign:", text, name)
            self.assertIn("$aidesign", text, name)
            self.assertIn("THIRD_PARTY_NOTICES.md", text, name)


class ManualCi(unittest.TestCase):

    def setUp(self):
        self.text = read(os.path.join(REPO, ".github", "workflows", "ci.yml"))

    def test_runs_only_by_hand(self):
        self.assertIn("workflow_dispatch:", self.text)
        for trigger in ("push:", "pull_request:", "schedule:", "release:"):
            self.assertNotIn(trigger, self.text)

    def test_runs_the_unit_tests_on_three_systems(self):
        for system in ("ubuntu-latest", "macos-latest", "windows-latest"):
            self.assertIn(system, self.text)
        # python, а не python3: на windows-latest setup-python ставит только python.exe
        self.assertIn("run: python -B -m unittest discover -s tests", self.text)


def load_export():
    spec = importlib.util.spec_from_file_location("public_export", EXPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git"), "git не установлен")
class PublicExport(unittest.TestCase):
    """tools/public-export.py: выгрузка из git ls-files без рабочих папок и с проверкой."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ad-export-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, ".aispa-work"))
        files = {
            "LICENSE": "MIT\nbase: " + "Auto" + "pilot 2.2.0\n",
            "README.md": "# X\n\ntext\n\n[MIT](LICENSE) " + "Auto" + "pilot\n",
            "a.md": "clean\n",
            "БРИФ.md": "secret brief " + "/Use" + "rs/x\n",
            ".aispa-work/log.md": "/Use" + "rs/someone\n",
            "untracked.md": "not in git\n",
        }
        for rel, text in files.items():
            with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
                f.write(text)
        git(self.repo, "init", "-q")
        git(self.repo, "add", "LICENSE", "README.md", "a.md", "БРИФ.md", ".aispa-work/log.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_export(self, *extra):
        out = os.path.join(self.tmp, "out")
        r = subprocess.run([sys.executable, "-B", EXPORT, "--repo", self.repo, "--out", out, *extra],
                           capture_output=True, text=True, timeout=60)
        return r, out

    def test_clean_export_skips_work_files_and_prints_the_path(self):
        r, out = self.run_export()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(out, r.stdout)
        got = sorted(os.path.relpath(os.path.join(b, n), out) for b, _, ns in os.walk(out) for n in ns)
        self.assertEqual(got, ["LICENSE", "README.md", "a.md"])

    def test_dirty_export_names_the_file_and_fails(self):
        cases = {
            "path.md": "see " + "/Use" + "rs/me/x\n",
            "mail.md": "write me" + "@" + "mail.ru\n",
            "token.md": "gh" + "p_" + "a" * 36 + "\n",
            "base.md": "made from " + "auto" + "pilot\n",
        }
        for name, text in cases.items():
            with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
                f.write(text)
        git(self.repo, "add", *cases)
        r, _ = self.run_export()
        self.assertEqual(r.returncode, 1, r.stdout)
        for name in cases:
            self.assertIn(name, r.stdout + r.stderr)

    def test_base_word_outside_the_last_readme_line_is_caught(self):
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as f:
            f.write("# X\n" + "Auto" + "pilot inside\n\n[MIT](LICENSE) ok\n")
        r, _ = self.run_export()
        self.assertEqual(r.returncode, 1)
        self.assertIn("README.md", r.stdout + r.stderr)

    def test_names_files_that_are_not_in_git_and_so_not_exported(self):
        r, out = self.run_export()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Не в git, не выгружено: untracked.md", r.stdout)
        self.assertNotIn("БРИФ.md", r.stdout.split("Не в git", 1)[-1])
        self.assertFalse(os.path.exists(os.path.join(out, "untracked.md")))

    def test_refuses_a_non_empty_out_dir(self):
        out = os.path.join(self.tmp, "out")
        os.makedirs(out)
        with open(os.path.join(out, "keep.txt"), "w") as f:
            f.write("x")
        r, _ = self.run_export()
        self.assertEqual(r.returncode, 2)
        self.assertTrue(os.path.isfile(os.path.join(out, "keep.txt")))

    def test_the_real_repository_exports_clean(self):
        # Выгрузка берёт файлы из git: в самой выгрузке (и в любой копии без .git) проверять нечего.
        if not os.path.exists(os.path.join(REPO, ".git")):
            self.skipTest("нет .git — это выгрузка или копия без истории; выгрузку проверяют в репозитории")
        r = subprocess.run([sys.executable, "-B", EXPORT, "--repo", REPO, "--out", os.path.join(self.tmp, "real")],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def header_sources(path):
    """Из шапок файла: [(репо, имя файла или скилла)] — что названо после адреса репозитория."""
    found = []
    for line in read(path).splitlines():
        m = re.match(r"<!-- (?:Источник|По мотивам): (\S+/\S+?)(?=[\s,(])(.*)", line)
        if not m:
            continue
        repo, rest = m.group(1), re.split(r"[,(]", m.group(2), maxsplit=1)[0]
        for token in rest.split():
            if token == "и":
                continue
            parts = token.strip("/").split("/")
            name = parts[-2] if parts[-1] == "SKILL.md" and len(parts) > 1 else parts[-1]
            found.append((repo, name))
    return found


class NoticesMatchMotionHeaders(unittest.TestCase):

    def test_every_file_named_in_a_motion_header_is_named_in_the_notices(self):
        sections = re.split(r"^### ", read(os.path.join(REPO, "THIRD_PARTY_NOTICES.md")), flags=re.M)
        checked = 0
        for name in sorted(os.listdir(MOTION)):
            for repo, item in header_sources(os.path.join(MOTION, name)):
                section = [s for s in sections if "`%s`" % repo in s.split("\n", 1)[0]]
                self.assertTrue(section, "%s: нет раздела для %s" % (name, repo))
                taken = section[0].split("- **Не взято:**")[0]
                self.assertIn(item, taken, "%s: %s — в «Что взято» нет %s" % (name, repo, item))
                checked += 1
        self.assertGreaterEqual(checked, 30)


if __name__ == "__main__":
    unittest.main()
