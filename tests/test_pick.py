"""Тесты skills/aidesign/tools/pick.py — справочник стилей, палитр, шрифтовых пар и отраслей.

Шов — CLI отдельным процессом (как агент). Контраст и «синие как Tailwind» тест считает
своими формулами (WCAG 2.x и OKLab), а не функциями pick.py. Поломки справочника — на
копии данных во временной папке (`--data`), настоящие файлы не трогаются.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "skills", "aidesign")
PICK = os.path.join(SKILL, "tools", "pick.py")
DS = os.path.join(SKILL, "tools", "designsystem.py")
DATA = os.path.join(SKILL, "knowledge", "справочник")
TAILWIND = ("#2563EB", "#3B82F6", "#6366F1")
TEXT_PAIRS = [("text", "bg"), ("text", "surface"), ("muted", "bg"), ("muted", "surface"),
              ("on-primary", "primary"), ("on-accent", "accent"), ("on-danger", "danger"),
              ("on-warning", "warning"), ("success", "bg")]
UI_PAIRS = [("border", "bg"), ("ring", "bg"), ("ring", "surface"), ("primary", "bg")]


def run(*args, data=None):
    cmd = [sys.executable, "-B", PICK] + list(args)
    if data:
        cmd += ["--data", data]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def load(name, data=DATA):
    with open(os.path.join(data, name), encoding="utf-8") as f:
        return json.load(f)


def dump(obj, name, data):
    with open(os.path.join(data, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def channel(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def contrast(a, b):
    la, lb = (0.2126 * channel(x) + 0.7152 * channel(y) + 0.0722 * channel(z) for x, y, z in (rgb(a), rgb(b)))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def oklab(hexstr):
    r, g, b = (channel(x) for x in rgb(hexstr))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def delta_e(a, b):
    return sum((x - y) ** 2 for x, y in zip(oklab(a), oklab(b))) ** 0.5 * 100


class Volume(unittest.TestCase):
    def test_reference_has_at_least_the_promised_amount(self):
        self.assertGreaterEqual(len(load("стили.json")["styles"]), 40)
        self.assertGreaterEqual(len(load("палитры.json")["palettes"]), 150)
        self.assertGreaterEqual(len(load("шрифты-пары.json")["pairs"]), 80)
        self.assertGreaterEqual(len(load("отрасли.json")["industries"]), 60)
        self.assertGreaterEqual(len(load("лендинги.json")["landings"]), 20)

    def test_readme_describes_every_data_file(self):
        with open(os.path.join(DATA, "README.md"), encoding="utf-8") as f:
            text = f.read()
        for name in ("стили.json", "палитры.json", "шрифты-пары.json", "отрасли.json",
                     "лендинги.json", "google-fonts.json", "pick.py validate"):
            self.assertIn(name, text)


class Validate(unittest.TestCase):
    def test_real_reference_has_zero_violations(self):
        r = run("validate")
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("Нарушений: 0", r.stdout)

    def broken(self, mutate):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        data = os.path.join(tmp, "справочник")
        shutil.copytree(DATA, data)
        mutate(data)
        return run("validate", "--json", data=data)

    def test_low_contrast_text_is_a_violation(self):
        def mutate(data):
            p = load("палитры.json", data)
            p["palettes"][0]["light"]["muted"] = p["palettes"][0]["light"]["bg"]
            dump(p, "палитры.json", data)
        r = self.broken(mutate)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any("контраст" in v for v in json.loads(r.stdout)["violations"]))

    def test_pair_with_a_font_without_cyrillic_is_a_violation(self):
        def mutate(data):
            p = load("шрифты-пары.json", data)
            p["pairs"][0]["heading"] = "Bebas Neue"          # в Google Fonts без кириллицы
            dump(p, "шрифты-пары.json", data)
        r = self.broken(mutate)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any("Bebas Neue" in v for v in json.loads(r.stdout)["violations"]))

    def test_duplicate_id_and_wrong_font_link_are_violations(self):
        def mutate(data):
            s = load("стили.json", data)
            s["styles"].append(dict(s["styles"][0]))
            dump(s, "стили.json", data)
            p = load("шрифты-пары.json", data)
            p["pairs"][1]["url"] = "https://fonts.example.com/css?family=X"
            dump(p, "шрифты-пары.json", data)
        r = self.broken(mutate)
        found = json.loads(r.stdout)["violations"]
        self.assertTrue(any("повтор" in v for v in found), found)
        self.assertTrue(any("ссылк" in v for v in found), found)

    def test_palette_tokens_go_through_check_py_in_both_themes(self):
        def mutate(data):
            p = load("палитры.json", data)
            light = p["palettes"][0]["light"]
            light.update({"bg": "#F5EBDD", "surface": "#FBF5EC", "primary": "#B5512F", "ring": "#B5512F"})
            p["palettes"][0].pop("dark", None)
            dump(p, "палитры.json", data)
        r = self.broken(mutate)
        self.assertEqual(r.returncode, 1)
        found = [v for v in json.loads(r.stdout)["violations"] if "cream-terracotta" in v]
        self.assertTrue(found, r.stdout[-1500:])
        self.assertIn("check.py", found[0])

    def test_unknown_rule_condition_is_a_violation(self):
        def mutate(data):
            o = load("отрасли.json", data)
            o["industries"][0]["rules"]["if_moon_phase"] = ["style:" + o["industries"][0]["styles"][0]]
            dump(o, "отрасли.json", data)
        r = self.broken(mutate)
        self.assertTrue(any("if_moon_phase" in v for v in json.loads(r.stdout)["violations"]))


class Palettes(unittest.TestCase):
    """Контраст и шаблонность — своими формулами, независимо от pick.py."""

    @classmethod
    def setUpClass(cls):
        r = run("list", "palettes", "--json")
        assert r.returncode == 0, r.stderr
        cls.items = json.loads(r.stdout)["items"]

    def test_every_palette_passes_contrast_in_light_and_dark(self):
        bad = []
        for p in self.items:
            for mode in ("light", "dark"):
                roles = p[mode]
                for fg, bg in TEXT_PAIRS:
                    if contrast(roles[fg], roles[bg]) < 4.5:
                        bad.append("%s %s %s/%s" % (p["id"], mode, fg, bg))
                for fg, bg in UI_PAIRS:
                    if contrast(roles[fg], roles[bg]) < 3:
                        bad.append("%s %s %s/%s" % (p["id"], mode, fg, bg))
        self.assertEqual(bad, [])

    def test_tailwind_blues_are_at_most_five_percent(self):
        like = [p["id"] for p in self.items
                if any(delta_e(p["light"][r], t) < 10 for r in ("primary", "accent") for t in TAILWIND)]
        self.assertLessEqual(len(like) / len(self.items), 0.05, like)

    def test_palettes_have_names_moods_and_purpose(self):
        for p in self.items:
            for field in ("name", "mood", "for"):
                self.assertTrue(p.get(field), "%s: нет %s" % (p["id"], field))
        self.assertEqual(len({p["name"] for p in self.items}), len(self.items), "имена повторяются")


class Pick(unittest.TestCase):
    def pick(self, query, *extra):
        r = run(query, "--json", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_three_businesses_get_different_reasoned_candidates(self):
        got = {q: self.pick(q) for q in ("кофейня уютная", "юрист строгий", "детская школа рисования")}
        industries = {q: g["industry"]["id"] for q, g in got.items()}
        self.assertEqual(len(set(industries.values())), 3, industries)
        for kind in ("styles", "palettes", "pairs"):
            tops = {g[kind][0]["id"] for g in got.values()}
            self.assertEqual(len(tops), 3, (kind, tops))
        for g in got.values():
            self.assertTrue(g["hypothesis"])
            for kind in ("styles", "palettes", "pairs", "landings"):
                self.assertTrue(g[kind], kind)
                for item in g[kind]:
                    self.assertTrue(item["reasons"], (kind, item["id"]))

    def test_russian_word_forms_find_the_same_industry(self):
        a = self.pick("кофейня")["industry"]["id"]
        self.assertEqual(self.pick("открываю кофейню у дома")["industry"]["id"], a)
        self.assertEqual(self.pick("сайт для юристов")["industry"]["id"],
                         self.pick("юридическая консультация")["industry"]["id"])

    # «Профессия + определение»: отрасль — по главному слову дела, а не по любому совпадению.
    # Ожидания разобраны вручную по смыслу запроса (слепая приёмка 0.4.0: «юрист по семейным делам»).
    PROFESSIONS = {
        "юрист по семейным делам": "lawyer", "семейный юрист": "lawyer", "адвокат по уголовным делам": "lawyer",
        "сайт для юристов": "lawyer", "юридическая консультация": "lawyer",
        "детский стоматолог": "dentist", "семейная стоматология": "dentist", "детский стоматолог в центре города": "dentist",
        "свадебный фотограф": "photographer", "детский фотограф": "photographer",
        "женский фитнес": "fitness", "кофейня у дома": "coffee", "уютная чайная": "tea-shop",
        "семейный психолог": "psychologist", "детский психолог": "psychologist",
        "консультация психолога": "psychologist", "свадебный флорист": "florist", "детский массаж": "massage",
        "семейное кафе": "family-cafe", "детское кафе": "family-cafe", "мужская стрижка": "barbershop",
        "элитный барбершоп": "barbershop", "стрижка собак": "grooming", "ветеринар для кошек": "vet",
        "частный детский сад": "kids-center", "семейный врач": "clinic", "домашняя пекарня": "bakery",
        "свадебный торт на заказ": "confectionery", "детская школа танцев": "dance-school",
        "английский для детей": "language-school", "репетитор по математике": "tutor",
        "налоговый бухгалтер": "accounting", "семейный нотариус": "notary",
        "личный финансовый консультант": "finance-advisor", "персональный тренер по боксу": "personal-trainer",
        "свадебное агентство": "wedding", "ремонт квартир под ключ": "renovation", "семейная гостиница": "hotel",
        "семейная ферма": "farm", "ресторан грузинской кухни": "restaurant", "мастер маникюра на дому": "nails",
        "детский театр": "theater", "вечерний бар": "bar",
    }

    def test_profession_with_a_qualifier_finds_the_profession(self):
        self.assertGreaterEqual(len(self.PROFESSIONS), 30)
        for query, want in self.PROFESSIONS.items():
            with self.subTest(query=query):
                self.assertEqual(self.pick(query)["industry"]["id"], want)

    def test_three_directions_come_from_different_style_families(self):
        g = self.pick("барбершоп смелый", "--n", "3")
        families = {d["style"]["family"] for d in g["directions"]}
        self.assertEqual(len(g["directions"]), 3)
        self.assertEqual(len(families), 3, families)

    def test_tokens_file_passes_designsystem_export(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        out = os.path.join(tmp, "design-system", "tokens.css")
        r = run("кофейня уютная", "--tokens", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = subprocess.run([sys.executable, "-B", DS, "export", "--root", tmp],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(e.returncode, 0, e.stdout + e.stderr)
        with open(os.path.join(tmp, "design-system", "tokens.json"), encoding="utf-8") as f:
            tokens = json.load(f)
        for role in ("bg", "text", "primary", "on-primary", "ring"):
            self.assertIn(role, tokens["color"])
            self.assertIn(role, tokens["$themes"]["dark"]["color"])
        self.assertIn("display", tokens["font"])
        self.assertIn("body", tokens["font"])
        self.assertGreaterEqual(contrast(tokens["color"]["text"], tokens["color"]["bg"]), 4.5)

    def test_tokens_do_not_overwrite_someone_elses_file(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        out = os.path.join(tmp, "tokens.css")
        theirs = ":root { --color-bg: #fff; }\n"
        with open(out, "w", encoding="utf-8") as f:
            f.write(theirs)
        r = run("кофейня уютная", "--tokens", out)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--force", r.stderr)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), theirs)
        r = run("кофейня уютная", "--tokens", tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        r = run("кофейня уютная", "--tokens", out, "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            self.assertIn("Черновик токенов AI Design из справочника", f.read())
        r = run("кофейня уютная", "--tokens", out, "--direction", "2")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_industry_is_an_input_error(self):
        self.assertEqual(run("кофейня", "--industry", "нет-такой").returncode, 2)


if __name__ == "__main__":
    unittest.main()
