"""Целостность базы знаний AI Design: индекс, шапки атрибуции, источники.

Запуск из корня репозитория:  python3 -B -m unittest tests.test_knowledge
Швы — чтение файлов:
- каждая ссылка из knowledge/INDEX.md и knowledge/язык/стили/INDEX.md ведёт на существующий файл,
  и каждый файл знаний назван в одном из индексов;
- каждый файл знаний начинается с шапки атрибуции; перенесённый — с пометкой «Изменено»;
- каждый источник из шапок скилла назван в THIRD_PARTY_NOTICES.md;
- реестр knowledge/sources.json сходится с THIRD_PARTY_NOTICES.md, обоими README и шапками атрибуции.
"""

import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILL = os.path.join(REPO, "skills", "aidesign")
KNOWLEDGE = os.path.join(SKILL, "knowledge")
STYLES = os.path.join(KNOWLEDGE, "язык", "стили")
NOTICES = os.path.join(REPO, "THIRD_PARTY_NOTICES.md")

REGISTRY = os.path.join(KNOWLEDGE, "sources.json")
READMES = [os.path.join(REPO, n) for n in ("README.md", "README.ru.md")]

HEADER = re.compile(r"^<!-- (Источник|По мотивам): (\S+?)[,\s(]")
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
OWN_REPOS = {"alexfisenkov/aispa", "alexfisenkov/aidesign"}   # наши собственные, не сторонние источники
FIELDS = ("id", "title", "repo", "url", "license", "form", "taken", "files")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def md_files(root):
    found = []
    for base, _dirs, names in os.walk(root):
        for name in names:
            if name.endswith(".md"):
                found.append(os.path.join(base, name))
    return sorted(found)


def header_lines(path):
    """Строки-комментарии шапки атрибуции в начале файла (подряд с первой строки)."""
    lines = []
    for line in read(path).splitlines():
        if line.startswith("<!--"):
            lines.append(line)
        else:
            break
    return lines


def repo_of(line):
    """`owner/name` из шапки: `pbakaus/impeccable/skill/...` → `pbakaus/impeccable`."""
    m = HEADER.match(line)
    if not m:
        return None
    parts = m.group(2).split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else None


class IndexMatchesFiles(unittest.TestCase):

    def links(self, index):
        base = os.path.dirname(index)
        return {os.path.normpath(os.path.join(base, m)) for m in LINK.findall(read(index))}

    def test_every_link_in_the_indexes_points_at_an_existing_file(self):
        for index in (os.path.join(KNOWLEDGE, "INDEX.md"), os.path.join(STYLES, "INDEX.md")):
            for target in self.links(index):
                self.assertTrue(os.path.isfile(target), "%s ссылается на %s" % (index, target))

    def test_every_knowledge_file_is_named_in_an_index(self):
        named = self.links(os.path.join(KNOWLEDGE, "INDEX.md")) | self.links(os.path.join(STYLES, "INDEX.md"))
        indexes = {os.path.join(KNOWLEDGE, "INDEX.md"), os.path.join(STYLES, "INDEX.md")}
        for path in md_files(KNOWLEDGE):
            if path in indexes:
                continue
            self.assertIn(path, named, "файл знаний не назван в индексе: %s" % os.path.relpath(path, KNOWLEDGE))

    def test_the_project_files_of_iteration_19_are_in_the_main_index(self):
        links = self.links(os.path.join(KNOWLEDGE, "INDEX.md"))
        for name in ("инструменты.md", "структура-проекта.md"):
            self.assertIn(os.path.join(KNOWLEDGE, name), links, name)

    def test_the_style_index_is_reachable_from_the_main_index(self):
        self.assertIn(os.path.join(STYLES, "INDEX.md"), self.links(os.path.join(KNOWLEDGE, "INDEX.md")))

    def test_the_two_fixed_folders_exist_with_their_files(self):
        for name in ("антипаттерны.md", "типографика.md", "цвет.md", "сетка-и-ритм.md", "сочетание.md",
                     "решения-споров.md", "доступность-и-качество.md", "design-md.md",
                     "извлечь-стиль-с-сайта.md"):
            self.assertTrue(os.path.isfile(os.path.join(KNOWLEDGE, "язык", name)), name)
        for name in ("движение.md", "прокрутка-и-сцены.md", "морфинг.md", "курсор-и-микровзаимодействия.md",
                     "webgl-и-3d.md", "фото.md", "видео.md", "видео-в-сайт.md", "превью.md",
                     "готовый-сайт.md", "поверхности.md"):
            self.assertTrue(os.path.isfile(os.path.join(KNOWLEDGE, "движение-и-медиа", name)), name)


class AttributionHeaders(unittest.TestCase):

    def test_every_knowledge_file_starts_with_an_attribution_header(self):
        for path in md_files(KNOWLEDGE):
            first = read(path).splitlines()[0]
            self.assertRegex(first, r"^<!-- (Источник|По мотивам): ", os.path.relpath(path, KNOWLEDGE))

    def test_a_source_header_names_the_license_and_what_was_changed(self):
        for path in md_files(KNOWLEDGE):
            for line in header_lines(path):
                if line.startswith("<!-- Источник:"):
                    where = os.path.relpath(path, KNOWLEDGE)
                    self.assertRegex(line, r"\b(MIT|Apache-2\.0)\b", where)
                    self.assertIn("Изменено:", line, where)
                    self.assertTrue(line.rstrip().endswith("-->"), where)

    def test_a_motive_header_closes_its_comment(self):
        for path in md_files(KNOWLEDGE):
            for line in header_lines(path):
                self.assertTrue(line.rstrip().endswith("-->"), os.path.relpath(path, KNOWLEDGE))


class SourcesAreCredited(unittest.TestCase):

    def test_every_source_named_in_a_header_is_in_third_party_notices(self):
        notices = read(NOTICES).lower()
        seen = set()
        for path in md_files(SKILL):
            for line in header_lines(path):
                repo = repo_of(line)
                if repo and repo.lower() not in OWN_REPOS:
                    seen.add(repo)
                    self.assertIn(repo.lower(), notices, "%s: %s" % (os.path.relpath(path, SKILL), repo))
        self.assertGreaterEqual(len(seen), 10)

    def test_third_party_notices_carry_a_license_and_an_address_for_every_source(self):
        text = read(NOTICES)
        sections = re.split(r"^### ", text.split("## Взятые материалы", 1)[1].split("## Товарные знаки", 1)[0],
                            flags=re.M)[1:]
        self.assertGreaterEqual(len(sections), 18)
        for section in sections:
            title = section.splitlines()[0]
            self.assertTrue("**Лицензия:**" in section or "**Условия:**" in section, title)
            self.assertIn("**Что взято:**", section, title)

    def test_both_license_texts_are_present(self):
        text = read(NOTICES)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn("Apache License", text)
        self.assertIn("END OF TERMS AND CONDITIONS", text)


def notice_sections(text):
    """Разделы «### …» из «Взятые материалы» THIRD_PARTY_NOTICES.md."""
    body = text.split("## Взятые материалы", 1)[1].split("## Товарные знаки", 1)[0]
    return ["### " + s for s in re.split(r"^### ", body, flags=re.M)[1:]]


def section_of(entry, sections):
    """Раздел уведомлений для записи реестра: по `репо` в заголовке или, без репо, по адресу."""
    for s in sections:
        head = s.split("\n", 1)[0]
        if entry.get("repo") and "`%s`" % entry["repo"] in head:
            return s
        if not entry.get("repo") and entry.get("url") and entry["url"] in s:
            return s
    return None


def header_repos():
    """{путь файла скилла от SKILL: {репо из шапок}} без наших собственных."""
    out = {}
    for path in md_files(SKILL):
        repos = {repo_of(l) for l in header_lines(path)} - {None}
        repos = {r for r in repos if r.lower() not in OWN_REPOS}
        if repos:
            out[os.path.relpath(path, SKILL).replace(os.sep, "/")] = repos
    return out


def registry_problems(sources, notices, readmes, headers):
    """Расхождения реестра источников с уведомлениями, README и шапками атрибуции.

    sources — записи sources.json; notices — текст THIRD_PARTY_NOTICES.md; readmes — {имя: текст};
    headers — {путь файла скилла: {репо из шапки}}. Пустой список — всё сходится.
    """
    problems = []
    sections = notice_sections(notices)
    known = {s["repo"].lower() for s in sources if s.get("repo")}
    for s in sources:
        name = s.get("id", "?")
        for field in FIELDS:
            if field not in s:
                problems.append("%s: нет поля %s" % (name, field))
        if section_of(s, sections) is None:
            problems.append("%s: нет в THIRD_PARTY_NOTICES.md" % name)
        for readme, text in readmes.items():
            if s.get("url") and s["url"] not in text:
                problems.append("%s: нет адреса в %s" % (name, readme))
        for path in s.get("files", []):
            if s.get("repo") and s["repo"] not in headers.get(path, set()):
                problems.append("%s: в шапке %s нет %s" % (name, path, s["repo"]))
    for sec in sections:
        if not any(section_of(s, [sec]) for s in sources):
            problems.append("раздел уведомлений без записи в реестре: %s" % sec.split("\n", 1)[0])
    for path, repos in sorted(headers.items()):
        for repo in sorted(repos):
            if repo.lower() not in known:
                problems.append("%s: источник %s не в реестре" % (path, repo))
    return problems


class SourceRegistry(unittest.TestCase):
    """knowledge/sources.json ↔ THIRD_PARTY_NOTICES.md ↔ оба README ↔ шапки атрибуции."""

    def setUp(self):
        with open(REGISTRY, encoding="utf-8") as f:
            self.registry = json.load(f)
        self.sources = self.registry["sources"]
        self.notices = read(NOTICES)
        self.readmes = {os.path.basename(p): read(p) for p in READMES}

    def test_registry_is_complete_and_matches_everything(self):
        self.assertGreaterEqual(len(self.sources), 14)
        self.assertEqual(len({s["id"] for s in self.sources}), len(self.sources), "id повторяются")
        self.assertEqual(registry_problems(self.sources, self.notices, self.readmes, header_repos()), [])

    def test_every_attributed_file_is_listed_under_its_source(self):
        listed = {(p, s["repo"]) for s in self.sources if s.get("repo") for p in s["files"]}
        for path, repos in header_repos().items():
            for repo in repos:
                self.assertIn((path, repo), listed, "%s → %s нет в files реестра" % (path, repo))

    def test_a_source_missing_from_the_notices_is_caught(self):
        extra = dict(self.sources[0], id="new-skill", repo="someone/new-skill",
                     url="https://github.com/someone/new-skill", files=[])
        readmes = {k: v + "\n" + extra["url"] for k, v in self.readmes.items()}
        problems = registry_problems(self.sources + [extra], self.notices, readmes, header_repos())
        self.assertEqual(problems, ["new-skill: нет в THIRD_PARTY_NOTICES.md"])

    def test_a_header_source_missing_from_the_registry_is_caught(self):
        headers = dict(header_repos(), **{"knowledge/x.md": {"someone/other"}})
        problems = registry_problems(self.sources, self.notices, self.readmes, headers)
        self.assertEqual(problems, ["knowledge/x.md: источник someone/other не в реестре"])

    def test_the_how_to_add_a_source_doc_names_every_step(self):
        doc = read(os.path.join(REPO, "docs", "пополнение.md"))
        for word in ("лицензи", "sources.json", "THIRD_PARTY_NOTICES.md", "README", "<!-- Источник:",
                     "<!-- По мотивам:", "knowledge/INDEX.md", "python3 -B -m unittest discover -s tests",
                     "public-export.py"):
            self.assertIn(word, doc, word)


if __name__ == "__main__":
    unittest.main()
