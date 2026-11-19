"""Тесты процесса AI Design: SKILL.md, phases/*.md, prompts/*.md.

Запуск из корня репозитория:  python3 -B -m unittest tests.test_process
Швы — чтение файлов скилла и вызов настоящего ad.py во временной папке:
- банк вопросов интервью устроен по правилу (одна мысль, 2–4 варианта, рекомендация);
- каждая команда ad.py, названная в фазах, существует;
- каждый файл знаний, названный в фазах, есть на диске и в knowledge/INDEX.md.
"""

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILL = os.path.join(REPO, "skills", "aidesign")
PHASES = os.path.join(SKILL, "phases")
PROMPTS = os.path.join(SKILL, "prompts")
KNOWLEDGE = os.path.join(SKILL, "knowledge")
AD = os.path.join(SKILL, "tools", "ad.py")

PHASE_FILES = ["0-start.md", "1-refs.md", "2-interview.md", "3-previews.md",
               "4-build.md", "5-check.md", "6-handoff.md", "figma.md"]
PROMPT_FILES = ["preview.md", "build.md", "critic.md"]
STAGE_WORDS = ["Подготовка", "Референсы", "Интервью", "Превью", "Сборка", "Проверка", "Передача"]
# Темы, которые интервью обязано закрыть (спецификация, история 14).
REQUIRED_THEMES = ["Поверхность", "Цель и аудитория", "Характер", "Тон", "Плотность", "Цвет",
                   "Типографика", "Движение", "Фото и видео", "Антипримеры"]
JARGON = re.compile(r"\b(CTA|hero|UX|UI|вайб\w*|фрейм\w*|лендос\w*|юзер\w*|кейс\w*)\b", re.I)
OPTION = re.compile(r"^\s*[-*]?\s*([абвг])\)\s+\S")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def process_texts():
    """Все тексты процесса: SKILL.md, фазы (кроме шаблона панели), задания субагентам."""
    out = {"SKILL.md": read(os.path.join(SKILL, "SKILL.md"))}
    for name in PHASE_FILES:
        out["phases/" + name] = read(os.path.join(PHASES, name))
    for name in PROMPT_FILES:
        out["prompts/" + name] = read(os.path.join(PROMPTS, name))
    return out


def section(text, title):
    """Текст раздела второго уровня «## <title>…» до следующего «## »."""
    m = re.search(r"^## %s[^\n]*\n(.*?)(?=^## |\Z)" % re.escape(title), text, re.M | re.S)
    return m.group(1) if m else ""


def question_bank():
    """Банк вопросов из 2-interview.md: [{id, theme, title, figurative, text, options, advice}]."""
    bank = section(read(os.path.join(PHASES, "2-interview.md")), "Банк вопросов")
    out, theme = [], None
    for block in re.split(r"(?=^### |^#### )", bank, flags=re.M):
        if block.startswith("### "):
            theme = block.split("\n", 1)[0][4:].strip()
            continue
        if not block.startswith("#### "):
            continue
        head, _, body = block.partition("\n")
        m = re.match(r"#### (В\d+)\s+(.*)", head)
        if not m:
            continue
        lines = [l for l in body.splitlines() if l.strip()]
        out.append({
            "id": m.group(1), "theme": theme, "title": m.group(2),
            "figurative": "(образный)" in head,
            "text": lines[0].strip() if lines else "",
            "options": [l for l in lines if OPTION.match(l)],
            "advice": [l for l in lines if l.strip().startswith("Я бы:")],
        })
    return out


class SkillFile(unittest.TestCase):
    def setUp(self):
        self.text = read(os.path.join(SKILL, "SKILL.md"))
        self.front = self.text.split("\n---", 1)[0]

    def test_frontmatter(self):
        self.assertTrue(self.text.startswith("---\n"))
        self.assertRegex(self.front, r"(?m)^name: aidesign$")
        self.assertRegex(self.front, r"(?m)^description: \S")
        self.assertRegex(self.front, r"(?m)^argument-hint: \S")
        self.assertRegex(self.front, r"(?m)^metadata:\n  version: \"0\.2\.0\"$")
        self.assertNotIn("disable-model-invocation", self.text)

    def test_title_and_stage_words(self):
        self.assertIn("# AI Design — фронтенд-дизайн сайтов", self.text)
        for word in STAGE_WORDS:
            self.assertIn(word, self.text, word)

    def test_table_names_every_phase_file(self):
        for name in PHASE_FILES:
            self.assertIn("phases/" + name, self.text, name)
            self.assertTrue(os.path.isfile(os.path.join(PHASES, name)), name)

    def test_rules_that_never_lose(self):
        rules = section(self.text, "Неснимаемые правила")
        for words in (("факт", "выдум"), ("платн", "сумм"), ("чужи", "фото"), ("сборк", "выбор")):
            self.assertTrue(any(all(w in line.lower() for w in words) for line in rules.splitlines()),
                            "нет правила со словами %s" % (words,))

    def test_figma_phase_is_in_the_table_only_by_consent(self):
        rows = [l for l in self.text.splitlines() if l.startswith("|") and "phases/figma.md" in l]
        self.assertEqual(len(rows), 1, "строка Figma в таблице этапов")
        self.assertIn("только по согласию", rows[0])

    def test_memory_block_is_updated_after_every_event(self):
        self.assertIn("после каждого события", self.text)

    def test_family_mechanics_named(self):
        for word in ("auto", "important", "interview", "по одному", "дальше решай сам", "⚑", "«ок»"):
            self.assertIn(word, self.text, word)


class Phases(unittest.TestCase):
    def setUp(self):
        self.texts = process_texts()

    def test_every_phase_names_ad_py(self):
        for name in PHASE_FILES:
            self.assertRegex(self.texts["phases/" + name], r"ad\.py \w", name)

    def test_no_mac_paths_and_no_base_names(self):
        for name, text in self.texts.items():
            self.assertNotIn("/Use" + "rs/", text, name)          # по частям: тест не находит сам себя
            self.assertNotRegex(text, "(?i)auto" + "pilot|nick" + " vels", name)

    def test_refs_phase(self):
        t = self.texts["phases/1-refs.md"]
        for word in ("референсы/", "Pinterest", "refs.md", "ref add", "скачать"):
            self.assertIn(word, t, word)

    def test_interview_rules(self):
        t = self.texts["phases/2-interview.md"]
        for word in ("vkus.md", "interview.md", "карт", "⚑", "«ок»", "по одному", "дальше решай сам",
                     "theme add", "ask interview"):
            self.assertIn(word, t, word)

    def test_previews_ask_after_all_three_options(self):
        t = self.texts["phases/3-previews.md"]
        self.assertIn("round option", t)
        self.assertIn("ask previews", t)
        self.assertLess(t.index("round option"), t.index("ask previews"),
                        "ask previews раньше round option: round option закрывает ожидание")
        for word in ("round refine", "round choose", "round feedback", "смешать", "смелее", "спокойнее",
                     "что понравилось"):
            self.assertIn(word, t, word)

    def test_build_waits_for_choice(self):
        t = self.texts["phases/4-build.md"]
        self.assertRegex(t, r"(?i)без (явного )?выбора|до (явного )?выбора")
        self.assertIn("knowledge/INDEX.md", t)

    def test_existing_site_audit_before_previews(self):
        t = self.texts["phases/1-refs.md"] + self.texts["phases/0-start.md"]
        self.assertIn("готовый-сайт.md", t)
        self.assertIn("check.py", t)
        self.assertRegex(t, r"(?i)аудит")

    def test_handoff(self):
        t = self.texts["phases/6-handoff.md"]
        for word in ("DESIGN.md", "design-md.md", "<!-- aidesign:start -->", "<!-- aidesign:end -->",
                     "aispa:start", "CONTEXT.md", "docs/adr/", "finish"):
            self.assertIn(word, t, word)

    def test_prompts_forbid_skills_and_foreign_photos(self):
        for name in PROMPT_FILES:
            self.assertIn("Не вызывай скиллы", self.texts["prompts/" + name], name)
        self.assertRegex(self.texts["prompts/preview.md"], r"(?i)чужи[хе] фото")
        self.assertRegex(self.texts["prompts/preview.md"], r"(?i)плашк")

    def test_handoff_asks_about_the_commit_before_finish(self):
        t = self.texts["phases/6-handoff.md"]
        landing = t[t.index("## 7. Посадка"):]
        self.assertIn("ask action", landing)
        self.assertLess(landing.index("Закоммитить"), landing.index("ad.py finish"),
                        "вопрос о коммите после finish: панель уже заморожена, ждать ответа некому")
        self.assertLess(landing.index("ask action"), landing.index("ad.py finish"))

    def test_skill_md_is_honest_about_a_memory_file_aispa_sees_as_users(self):
        together = section(self.texts["SKILL.md"], "Вместе с AISpa")
        self.assertIn("файлом пользователя", together)
        for word in ("дополнени", "предложит", "в конце"):
            self.assertIn(word, together, word)
        self.assertIn("только с блоком", together)


def memory_block_template(text):
    """Шаблон блока памяти из 6-handoff.md: текст между метками aidesign внутри блока кода."""
    m = re.search(r"```markdown\n<!-- aidesign:start -->\n(.*?)<!-- aidesign:end -->\n```", text, re.S)
    return m.group(1) if m else ""


# Пункты блока aidesign по истории 55 спецификации: (что, слова, которые его выдают).
BLOCK_ITEMS = [
    ("где дизайн-система", ("design-system/", "tokens.css")),
    ("где DESIGN.md", ("DESIGN.md",)),
    ("проверка шаблонности", ("check.py",)),
    ("проверка дизайн-системы", ("designsystem.py check",)),
    ("снимки", ("390", "1280", "playwright screenshot")),
    ("где бэкапы", (".aidesign-work/backups/", "backup.py list")),
    ("команда отката", ("backup.py restore",)),
    ("Figma", ("Figma", "не подключена")),
    ("что нельзя", ("Чего нельзя",)),
    ("как продолжить без AI Design", ("без AI Design",)),
]
OTHER_RULE_FILES = ("GEMINI.md", ".cursorrules", ".cursor/rules/", ".github/copilot-instructions.md",
                    ".windsurfrules")


class Iteration19(unittest.TestCase):
    """Итерация 19.11: этапы зовут инструменты задачи 07 по их настоящим командам."""

    def setUp(self):
        self.texts = process_texts()

    def order(self, name, *words):
        t = self.texts[name]
        places = []
        for word in words:
            self.assertIn(word, t, "%s: нет «%s»" % (name, word))
            places.append(t.index(word))
        self.assertEqual(places, sorted(places), "%s: порядок %s" % (name, words))

    def test_start_checks_python_first_then_doctor_then_asks_then_plans_the_structure(self):
        t = self.texts["phases/0-start.md"]
        first = t.index("## ", t.index("# Подготовка"))
        self.assertIn("python3 --version", t[first:first + 1500], "проверка Python — первым разделом")
        self.order("phases/0-start.md", "python3 --version", "setup.py doctor", "ad.py ask action",
                   "setup.py install", "scaffold.py plan")
        for word in ("py -3", "xcode-select --install", "winget install", "Python.Python.3.12", "пароль",
                     "ad.py toolkit set", "scaffold.py apply"):
            self.assertIn(word, t, word)

    def test_build_makes_the_before_backup_and_the_design_system_first(self):
        t = self.texts["phases/4-build.md"]
        self.order("phases/4-build.md", "backup.py create", "ad.py backup add", "design-system/tokens.css",
                   "designsystem.py export")
        for word in ("styleguide.html", "design-system/README.md", "design-system/CHANGELOG.md", "как было",
                     "без исключений", "ask action", "scaffold.py plan", "--force"):
            self.assertIn(word, t, word)
        existing = t[t.index("Готовый сайт"):]
        self.assertIn("backup.py create", existing, "бэкап «до» на готовом сайте")

    def test_check_runs_the_design_system_check_and_the_screenshot_recipe(self):
        t = self.texts["phases/5-check.md"]
        for word in ("designsystem.py check", "--ds design-system", "playwright screenshot",
                     "knowledge/инструменты.md"):
            self.assertIn(word, t, word)

    def test_handoff_exports_tokens_backs_up_and_offers_figma(self):
        t = self.texts["phases/6-handoff.md"]
        for word in ("designsystem.py export", "backup.py create", "ad.py backup add", "designsystem.py pack",
                     "design-system/CHANGELOG.md", "phases/figma.md", "4 и больше"):
            self.assertIn(word, t, word)

    def test_memory_block_template_carries_every_item_of_story_55(self):
        t = self.texts["phases/6-handoff.md"]
        block = memory_block_template(t)
        self.assertTrue(block, "в 6-handoff.md нет шаблона блока между метками")
        for what, words in BLOCK_ITEMS:
            for word in words:
                self.assertIn(word, block, "%s: нет «%s»" % (what, word))
        self.assertIn("после каждого события", t)
        for name in OTHER_RULE_FILES:
            self.assertIn(name, t, name)

    def test_figma_phase(self):
        t = self.texts["phases/figma.md"]
        for word in ("https://mcp.figma.com/mcp", "claude mcp add --transport http figma",
                     "figma@claude-plugins-official", "codex mcp add figma --url", "codex mcp login figma",
                     "setup.py plan figma --host", "generate_figma_design", "use_figma", "1280", "390",
                     "Карта сайта", "Дизайн-система", "tokens.json", "20", "ведущий агент",
                     "ad.py figma set", "--mode free", "--mode paid", "эффектов"):
            self.assertIn(word, t, word)
        self.assertRegex(t, r"(?i)не покупа")

    def test_build_prompt_takes_style_only_from_the_design_system(self):
        t = self.texts["prompts/build.md"]
        for word in ("design-system/tokens.css", "designsystem.py check"):
            self.assertIn(word, t, word)


class QuestionBank(unittest.TestCase):
    def setUp(self):
        self.bank = question_bank()

    def test_size(self):
        self.assertGreaterEqual(len(self.bank), 40)
        self.assertGreaterEqual(sum(q["figurative"] for q in self.bank), 8)

    def test_ids_unique(self):
        ids = [q["id"] for q in self.bank]
        self.assertEqual(len(ids), len(set(ids)))

    def test_first_question_is_the_surface(self):
        self.assertTrue(self.bank)
        self.assertIn("Поверхность", self.bank[0]["theme"])

    def test_every_question_by_the_rule(self):
        for q in self.bank:
            with self.subTest(q=q["id"]):
                self.assertEqual(q["text"].count("?"), 1, "одна мысль — один вопрос: %s" % q["text"])
                self.assertTrue(2 <= len(q["options"]) <= 4, "вариантов %d" % len(q["options"]))
                letters = [OPTION.match(l).group(1) for l in q["options"]]
                self.assertEqual(letters, list("абвг"[:len(letters)]))
                self.assertEqual(len(q["advice"]), 1, "нужна одна строка «Я бы:»")
                self.assertRegex(q["advice"][0], r"Я бы: [абвг]\b|Я бы: не знаешь")
                self.assertNotRegex(" ".join([q["text"]] + q["options"]), JARGON)

    def test_required_themes_covered(self):
        themes = {q["theme"] for q in self.bank}
        for name in REQUIRED_THEMES:
            self.assertTrue(any(name in t for t in themes), name)


class AdCommands(unittest.TestCase):
    """Каждая команда ad.py из фаз существует — проверяется настоящим ad.py."""

    @classmethod
    def setUpClass(cls):
        cls.texts = process_texts()
        cls.root = tempfile.mkdtemp(prefix="ad-process-")
        cls.a = os.path.join(cls.root, ".aidesign-work")
        os.makedirs(cls.a)
        shutil.copy(AD, os.path.join(cls.a, "ad.py"))
        cls.env = dict(os.environ, AIDESIGN_NO_UPDATE_CHECK="1", AIDESIGN_STOP_DELAY="0",
                       PYTHONUTF8="1")
        r = cls.ad("init", "--slug", "t", "--title", "T")
        assert r.returncode == 0, r.stdout + r.stderr
        cls.doc = ast.get_docstring(ast.parse(read(AD))) or ""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def ad(cls, *args):
        return subprocess.run([sys.executable, "-B", os.path.join(cls.a, "ad.py")] + list(args) + ["--no-serve"],
                              cwd=cls.root, env=cls.env, capture_output=True, text=True, encoding="utf-8")

    def calls(self):
        out = set()
        for name, text in self.texts.items():
            for m in re.finditer(r"ad\.py ([a-z]+)((?: [a-z]+(?:=[\w-]+)?)?)", text):
                out.add((name, m.group(1), m.group(2).strip()))
        return out

    def test_phases_name_commands(self):
        self.assertGreaterEqual(len({c for _, c, _ in self.calls()}), 10)

    def test_every_named_command_exists(self):
        for name, cmd, sub in sorted(self.calls()):
            with self.subTest(file=name, call=("%s %s" % (cmd, sub)).strip()):
                if cmd == "init":
                    continue
                if cmd == "stage" and sub:
                    r = self.ad("stage", sub)
                elif cmd == "ask" and sub:
                    r = self.ad("ask", sub, "--note", "x")
                elif cmd == "add" and sub:
                    r = self.ad("add", sub, "x")
                elif cmd == "set" and sub:
                    r = self.ad("set", sub)
                elif cmd in ("ref", "theme", "round", "direction", "backup", "figma", "toolkit") and sub:
                    self.assertRegex(self.doc, r"ad\.py %s %s\b" % (cmd, sub))
                    continue
                else:
                    r = self.ad(cmd)
                self.assertNotIn("неизвестная команда", r.stdout)
                if cmd in ("stage", "ask", "add", "set") and sub:
                    self.assertEqual(r.returncode, 0, r.stdout)


CHECK = os.path.join(SKILL, "tools", "check.py")


class CheckTool(unittest.TestCase):
    """check.py: обход папок пропускает рабочие папки скиллов; шапка называет основу правил."""

    def test_work_folders_of_both_skills_are_skipped(self):
        root = tempfile.mkdtemp(prefix="ad-check-")
        try:
            bad = "p { text-align: justify; }\n"
            for rel in (".aidesign-work/rounds/01/a.css", ".aispa-work/x.css", "site/ok.css"):
                path = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(bad if "work" in rel else "p { color: #222; }\n")
            r = subprocess.run([sys.executable, "-B", CHECK, root, "--json"], capture_output=True,
                               text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_header_names_impeccable_and_the_shared_rule_ids(self):
        head = "\n".join(read(CHECK).splitlines()[:6])
        self.assertIn("По мотивам: pbakaus/impeccable antipatterns (Apache-2.0)", head)
        for rule_id in ("overused-font", "gradient-text", "bounce-easing", "marquee", "skipped-heading"):
            self.assertIn(rule_id, head, rule_id)


class KnowledgeLinks(unittest.TestCase):
    def test_named_files_exist_and_are_in_index(self):
        index = read(os.path.join(KNOWLEDGE, "INDEX.md"))
        linked = set(re.findall(r"\]\(([^)]+\.md)\)", index))
        named = set()
        for text in process_texts().values():
            named |= set(re.findall(r"knowledge/((?:язык|движение-и-медиа)/[\w./-]+?\.md)", text))
        self.assertGreaterEqual(len(named), 10)
        for path in sorted(named):
            with self.subTest(path=path):
                self.assertTrue(os.path.isfile(os.path.join(KNOWLEDGE, path)), path)
                self.assertIn(path, linked)


if __name__ == "__main__":
    unittest.main()
