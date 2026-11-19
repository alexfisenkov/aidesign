"""Тесты витрины «Примеры работ»: skills/aidesign/examples/.

Шов — файлы: examples/INDEX.json по формату interfaces.md (модуль 4а)
и самодостаточные страницы examples/<id>/index.html, которые панель
показывает во вкладке «Примеры работ».
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "skills" / "aidesign" / "examples"
INDEX = EXAMPLES / "INDEX.json"
CHECK = ROOT / "skills" / "aidesign" / "tools" / "check.py"

# Внешние адреса, без которых страница всё равно работает: шрифты с системным
# запасом и CDN для GSAP (если пример его подключает).
ALLOWED_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com", "cdn.jsdelivr.net"}
CYRILLIC = re.compile(r"[а-яё]", re.I)


def load_check():
    spec = importlib.util.spec_from_file_location("aidesign_check_examples", CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["aidesign_check_examples"] = module
    spec.loader.exec_module(module)
    return module


def load_index():
    return json.loads(INDEX.read_text(encoding="utf-8"))


def pages():
    return {entry["id"]: EXAMPLES / entry["file"] for entry in load_index()}


class IndexFormat(unittest.TestCase):
    def test_index_is_list_of_6_to_9_entries(self):
        data = load_index()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 6)
        self.assertLessEqual(len(data), 9)

    def test_entry_fields(self):
        for entry in load_index():
            with self.subTest(entry=entry.get("id")):
                self.assertEqual(set(entry), {"id", "title", "style", "techniques", "file"})
                self.assertRegex(entry["id"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertEqual(entry["file"], entry["id"] + "/index.html")
                self.assertIsInstance(entry["techniques"], list)
                self.assertTrue(entry["techniques"])

    def test_ids_and_styles_are_unique(self):
        data = load_index()
        self.assertEqual(len({e["id"] for e in data}), len(data))
        self.assertEqual(len({e["style"].lower() for e in data}), len(data), "у каждого примера свой стиль")

    def test_texts_are_russian(self):
        for entry in load_index():
            with self.subTest(entry=entry["id"]):
                for text in [entry["title"], entry["style"]] + entry["techniques"]:
                    self.assertRegex(text, CYRILLIC)

    def test_index_matches_folders(self):
        listed = {EXAMPLES / e["file"] for e in load_index()}
        on_disk = set(EXAMPLES.glob("*/index.html"))
        self.assertEqual(listed, on_disk)
        for path in listed:
            self.assertTrue(path.is_file(), path)

    def test_required_styles_and_techniques_covered(self):
        data = load_index()
        styles = " ".join(e["style"].lower() for e in data)
        techniques = " ".join(t.lower() for e in data for t in e["techniques"])
        for style in ["редакционный", "минимализм", "тёмный", "игривый", "брутализм"]:
            self.assertIn(style, styles)
        for technique in ["видео-герой", "сцена прокрутки", "морфинг", "эффект курсора"]:
            self.assertIn(technique, techniques)


class PageRules(unittest.TestCase):
    def test_check_py_finds_nothing(self):
        check = load_check()
        for ex_id, path in pages().items():
            with self.subTest(example=ex_id):
                findings = check.scan([str(path)])
                self.assertEqual([], ["%d [%s] %s" % (f.line, f.rule, f.message) for f in findings])

    def test_only_index_html_inside_example_folders(self):
        for folder in (p for p in EXAMPLES.iterdir() if p.is_dir()):
            with self.subTest(folder=folder.name):
                self.assertEqual(sorted(p.name for p in folder.iterdir()), ["index.html"])

    def test_no_plain_http_and_no_external_media(self):
        for ex_id, path in pages().items():
            html = path.read_text(encoding="utf-8")
            with self.subTest(example=ex_id):
                self.assertNotIn("http://", html)
                for host in re.findall(r"https://([^/\"')\s]+)", html):
                    self.assertIn(host, ALLOWED_HOSTS)
                for tag in re.findall(r"<(?:img|video|source|audio|iframe)\b[^>]*>", html, re.I):
                    self.assertNotRegex(tag, r"\ssrc(set)?\s*=\s*\"(https?:)?//", tag)
                self.assertNotRegex(html, r"url\(\s*['\"]?(https?:)?//")

    def test_page_basics(self):
        for ex_id, path in pages().items():
            html = path.read_text(encoding="utf-8")
            with self.subTest(example=ex_id):
                self.assertRegex(html, r"<html lang=\"ru\"")
                self.assertIn('name="viewport"', html)
                self.assertIn("prefers-reduced-motion", html)
                self.assertRegex(html, r"@media[^{]*max-width", "раскладка для телефона")
                self.assertRegex(html, r"<title>[^<]*[а-яё]", "заголовок вкладки по-русски")
                self.assertIn("вымышлен", html.lower(), "страница честно говорит, что содержание вымышлено")

    def test_gsap_only_from_cdn(self):
        for ex_id, path in pages().items():
            html = path.read_text(encoding="utf-8")
            with self.subTest(example=ex_id):
                self.assertNotRegex(html, r"GreenSock|gsap\.com/standard-license")
                for src in re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", html):
                    self.assertRegex(src, r"^https://(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)/.*[/@]\d+\.\d+\.\d+/",
                                     "внешний скрипт — только CDN с точной версией")


if __name__ == "__main__":
    unittest.main()
