"""Тесты правил для следующего агента: подраздел «Сейчас» блока aidesign пишет ad.py сам.

Шов — ad.py отдельным процессом во временном проекте (как в test_ad), рядом его копия
rules.py — так их кладёт init. Проверяется только то, что видно на диске.
"""

import json
import os
import re
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ad import Project, read, write, SKILL  # noqa: E402

RULES = os.path.join(SKILL, "tools", "rules.py")
START, END = "<!-- aidesign:start -->", "<!-- aidesign:end -->"
NOW = re.compile(r"<!-- aidesign:now:start -->(.*?)<!-- aidesign:now:end -->", re.S)
POINTER = "подробности — блок `aidesign`"


def now_of(text):
    m = NOW.search(text)
    return m.group(1) if m else ""


def without_now(text):
    return NOW.sub("", text)


class Rules(Project):
    def setUp(self):
        super().setUp()
        if os.path.isfile(RULES):
            shutil.copy(RULES, os.path.join(self.a, "rules.py"))

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def test_now_follows_each_event_and_nothing_else_changes(self):
        head = "# Мой проект\n\nПиши коротко.\n\n"
        agent = START + "\n## Дизайн (AI Design)\n\nПравила:\n1. Мой пункт агента.\n" + END + "\n"
        tail = "\n## После блока\nчужой текст\n"
        write(self.path("AGENTS.md"), head + agent + tail)
        self.init()
        self.ok("direction", "set", "--name", "Тёплая редакция", "--summary", "бумага и антиква", "--file", "DESIGN.md")
        text = read(self.path("AGENTS.md"))
        self.assertIn("Тёплая редакция", now_of(text))
        self.assertIn("DESIGN.md", now_of(text))
        self.assertIn("не подключена", now_of(text))
        first = without_now(text)
        self.assertTrue(text.startswith(head + START), text)
        self.assertTrue(text.endswith(END + "\n" + tail), text)
        self.assertIn("1. Мой пункт агента.", text)
        self.ok("backup", "add", "--id", "20261119-101500-до", "--reason", "до", "--bytes", "2048")
        text = read(self.path("AGENTS.md"))
        self.assertIn("20261119-101500-до", now_of(text))
        self.assertIn("backup.py restore --root . --id 20261119-101500-до", now_of(text))
        self.assertEqual(without_now(text), first)
        self.ok("figma", "set", "--url", "https://www.figma.com/design/abc/Site", "--mode", "free")
        text = read(self.path("AGENTS.md"))
        self.assertIn("https://www.figma.com/design/abc/Site", now_of(text))
        self.assertNotIn("не подключена", now_of(text))
        self.assertEqual(without_now(text), first)
        self.assertEqual(text.count(START), 1)
        self.assertEqual(text.count("<!-- aidesign:now:start -->"), 1)
        self.assertFalse(os.path.exists(self.path("CLAUDE.md")))       # AGENTS.md уже был — второго не нужно

    def test_only_own_claude_md_gets_the_block_and_no_agents_md(self):
        own = "# Мой проект\n\nПравила Claude.\n"
        write(self.path("CLAUDE.md"), own)
        self.init()
        self.ok("direction", "set", "--name", "Швейцарский", "--summary", "сетка", "--file", "DESIGN.md")
        text = read(self.path("CLAUDE.md"))
        self.assertTrue(text.startswith(own), text)
        self.assertIn(START, text)
        self.assertIn("Швейцарский", now_of(text))
        self.assertFalse(os.path.exists(self.path("AGENTS.md")))

    def test_empty_project_gets_agents_md_and_one_line_claude_md(self):
        self.init()
        self.ok("direction", "set", "--name", "Мастерская", "--summary", "тёплое", "--file", "DESIGN.md")
        self.assertIn("Мастерская", now_of(read(self.path("AGENTS.md"))))
        self.assertEqual(read(self.path("CLAUDE.md")), "@AGENTS.md\n")

    def test_own_agents_md_without_block_gets_it_at_the_end_and_no_claude_md(self):
        own = "# Правила\n\nкак есть"
        write(self.path("AGENTS.md"), own)
        self.init()
        self.ok("figma", "set", "--url", "https://www.figma.com/design/x/S", "--mode", "paid")
        text = read(self.path("AGENTS.md"))
        self.assertTrue(text.startswith(own + "\n"), text)
        self.assertTrue(text.rstrip().endswith(END), text)
        self.assertIn("https://www.figma.com/design/x/S", now_of(text))
        self.assertFalse(os.path.exists(self.path("CLAUDE.md")))

    def test_ready_site_files_wait_for_the_first_copy(self):
        own = "# Сайт\n"
        write(self.path("AGENTS.md"), own)
        write(self.path(".cursorrules"), "x\n")
        self.ok("init", "--slug", "s", "--title", "S", "--entry", "existing", "--skill-dir", self.skill)
        self.ok("toolkit", "set")
        self.ok("direction", "set", "--name", "А", "--summary", "б", "--file", "DESIGN.md")
        self.assertEqual(read(self.path("AGENTS.md")), own)               # копии «до» ещё нет — файлы человека не трогаем
        self.assertEqual(read(self.path(".cursorrules")), "x\n")
        self.assertFalse(os.path.exists(self.path("CLAUDE.md")))
        self.ok("backup", "add", "--id", "20261119-1-до", "--reason", "до", "--bytes", "1")
        self.assertIn("20261119-1-до", now_of(read(self.path("AGENTS.md"))))
        self.assertIn(POINTER, read(self.path(".cursorrules")))

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "ссылки — на Unix")
    def test_pointer_file_that_links_to_the_memory_file_gets_nothing(self):
        write(self.path("AGENTS.md"), "# Проект\n")
        os.symlink("AGENTS.md", self.path("GEMINI.md"))
        write(self.path("CLAUDE.md"), "@AGENTS.md\n")
        os.makedirs(self.path(".github"))
        os.symlink(os.path.join("..", "CLAUDE.md"), self.path(".github", "copilot-instructions.md"))
        self.init()
        self.ok("direction", "set", "--name", "А", "--summary", "б", "--file", "DESIGN.md")
        self.ok("backup", "add", "--id", "20261119-1-до", "--reason", "до", "--bytes", "1")
        text = read(self.path("AGENTS.md"))
        self.assertNotIn(POINTER, text)
        self.assertTrue(text.rstrip().endswith(END), text)
        self.assertEqual(read(self.path("CLAUDE.md")), "@AGENTS.md\n")

    def test_markers_mentioned_in_text_or_code_are_not_a_block(self):
        own = ("# Проект\n\nМетки AI Design выглядят так: `" + START + "` и `" + END + "`.\n\n"
               "```markdown\n" + START + "\n## Дизайн (AI Design)\n<!-- aidesign:now:start -->\n"
               "<!-- aidesign:now:end -->\n" + END + "\n```\n")
        write(self.path("AGENTS.md"), own)
        self.init()
        self.ok("direction", "set", "--name", "Тёплая", "--summary", "б", "--file", "DESIGN.md")
        self.ok("figma", "set", "--url", "https://www.figma.com/design/x/S", "--mode", "free")
        text = read(self.path("AGENTS.md"))
        self.assertTrue(text.startswith(own), text)                       # текст и блок кода человека — как были
        tail = text[len(own):]
        self.assertIn(START, tail)
        self.assertIn("Тёплая", now_of(tail))
        self.assertIn("https://www.figma.com/design/x/S", now_of(tail))
        self.assertEqual(tail.count(START), 1)

    def test_now_markers_in_code_inside_the_block_are_left_alone(self):
        block = (START + "\n## Дизайн (AI Design)\n\nПример:\n```\n<!-- aidesign:now:start -->\nпример\n"
                 "<!-- aidesign:now:end -->\n```\n" + END + "\n")
        write(self.path("AGENTS.md"), "# П\n\n" + block)
        self.init()
        self.ok("direction", "set", "--name", "Тёплая", "--summary", "б", "--file", "DESIGN.md")
        text = read(self.path("AGENTS.md"))
        self.assertIn("```\n<!-- aidesign:now:start -->\nпример\n<!-- aidesign:now:end -->\n```", text)
        self.assertEqual(text.count("<!-- aidesign:now:start -->"), 2)
        self.assertIn("Тёплая", text)
        self.assertLess(text.index("Тёплая"), text.index("Пример:"))       # «Сейчас» — после заголовка, вне кода

    def test_pointer_lines_go_once_into_existing_rule_files_only(self):
        write(self.path(".cursorrules"), "use tabs")                    # без перевода строки в конце
        os.makedirs(self.path(".cursor", "rules"))
        self.init()
        self.ok("direction", "set", "--name", "А", "--summary", "б", "--file", "DESIGN.md")
        self.ok("backup", "add", "--id", "20261119-120000-после", "--reason", "после", "--bytes", "1")
        text = read(self.path(".cursorrules"))
        self.assertTrue(text.startswith("use tabs\n"), text)
        self.assertEqual(text.count(POINTER), 1, text)
        self.assertEqual(read(self.path(".cursor", "rules", "aidesign.mdc")).count(POINTER), 1)
        for name in ("GEMINI.md", ".windsurfrules", os.path.join(".github", "copilot-instructions.md")):
            self.assertFalse(os.path.exists(self.path(name)), name)

    def test_events_that_do_not_change_the_project_leave_rules_alone(self):
        self.init()
        self.ok("theme", "add", "--id", "tone", "--title", "Тон")
        self.ok("stage", "build")
        self.assertFalse(os.path.exists(self.path("AGENTS.md")))
        self.ok("stage", "build", "done")
        self.assertIn("Обновлено", now_of(read(self.path("AGENTS.md"))))

    def test_finish_and_toolkit_update_now(self):
        self.init()
        self.ok("toolkit", "set", "--missing", "ffmpeg")
        self.assertIn("ffmpeg", now_of(read(self.path("AGENTS.md"))))
        self.ok("finish", "--result", "готово")
        now = now_of(read(self.path("AGENTS.md")))
        self.assertIn(self.state()["dir"], now)
        self.assertNotIn("--wip", now)

    def test_design_system_on_disk_is_named(self):
        self.init()
        self.ok("direction", "set", "--name", "А", "--summary", "б", "--file", "DESIGN.md")
        self.assertIn("ещё нет", now_of(read(self.path("AGENTS.md"))))
        write(self.path("design-system", "tokens.css"), ":root{--color-ink:#111}")
        self.ok("stage", "build", "done")
        self.assertIn("design-system/tokens.css", now_of(read(self.path("AGENTS.md"))))

    def test_now_names_media_budget_spent_and_inventory(self):
        self.init()
        self.ok("media", "budget", "--limit", "100", "--unit", "кредитов")
        now = now_of(read(self.path("AGENTS.md")))
        self.assertRegex(now, r"Медиа:.*бюджет 100 кредитов, потрачено 0")
        self.assertIn("assets/media.json", now)
        self.ok("media", "spend", "--service", "higgsfield", "--amount", "30", "--item", "фон")
        self.ok("media", "spend", "--service", "magnific", "--amount", "12.5", "--item", "фото")
        now = now_of(read(self.path("AGENTS.md")))
        self.assertRegex(now, r"потрачено 42\.5 \(higgsfield 30, magnific 12\.5\)")
        write(self.path("assets", "media.json"), '{"items":[{"slot":"hero"},{"slot":"bg"}]}')
        self.ok("media", "sources", "--set", "generate")
        now = now_of(read(self.path("AGENTS.md")))
        self.assertIn("мест в описи: 2", now)
        self.assertIn("ad.py media check", now)

    def test_now_and_check_count_old_spends_without_unit_the_same_way(self):
        self.init()
        self.ok("media", "budget", "--limit", "100", "--unit", "кредиты")
        path = os.path.join(self.a, "state.js")
        s = json.loads(read(path).split("=", 1)[1])
        s["media"]["spent"] = [{"service": "higgsfield", "amount": 40, "item": "старая запись без единицы"}]
        write(path, "window.STATE =\n" + json.dumps(s, ensure_ascii=False) + "\n")
        code, out = self.ad("media", "check", "--amount", "61")
        self.assertEqual(code, 1, out)                                       # 40 + 61 > 100: старая трата считается
        self.ok("media", "sources", "--set", "own")
        self.assertRegex(now_of(read(self.path("AGENTS.md"))), r"потрачено 40 \(higgsfield 40\)")

    def test_now_says_no_budget_means_paid_only_with_permission(self):
        self.init()
        self.ok("direction", "set", "--name", "А", "--summary", "б", "--file", "DESIGN.md")
        self.assertRegex(now_of(read(self.path("AGENTS.md"))), r"Медиа: бюджета нет")

    def test_init_copies_rules_py(self):
        write(os.path.join(self.skill, "tools", "rules.py"), "# rules\n")
        self.init()
        self.assertEqual(read(os.path.join(self.a, "rules.py")), "# rules\n")


class Words(unittest.TestCase):
    """Процесс говорит агенту, что «Сейчас» пишет ad.py, а остальное — он сам."""

    def test_skill_and_handoff_split_the_block(self):
        for rel in ("SKILL.md", os.path.join("phases", "6-handoff.md"), os.path.join("phases", "0-start.md")):
            t = read(os.path.join(SKILL, rel))
            self.assertRegex(t, r"«Сейчас»[^\n]*`ad\.py`|`ad\.py`[^\n]*«Сейчас»", rel)
            self.assertIn("руками не", t, rel)
        t = read(os.path.join(SKILL, "phases", "6-handoff.md"))
        self.assertIn("<!-- aidesign:now:start -->", t)
        self.assertIn("**Агент пишет остальное**", t)


if __name__ == "__main__":
    unittest.main()
