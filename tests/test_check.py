"""Тесты проверки шаблонности skills/aidesign/tools/check.py.

Шов — функция scan(paths) -> list[Finding] и командная строка.
Образцы «плохо» и «хорошо» лежат прямо здесь: «плохо» собран из примет
каталога knowledge/язык/антипаттерны.md, «хорошо» — та же страница,
сделанная без них.
"""

import importlib.util
import os
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "skills" / "aidesign" / "tools" / "check.py"
CATALOG = ROOT / "skills" / "aidesign" / "knowledge" / "язык" / "антипаттерны.md"


def load_check():
    spec = importlib.util.spec_from_file_location("aidesign_check", CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["aidesign_check"] = module
    spec.loader.exec_module(module)
    return module


BAD_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Шаблон</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
<style>
:root { --bg: #0b0b0b; --accent: #39ff14; }
body { font-family: "Inter", sans-serif; background: #0b0b0b; color: #f5f5f5; }
p { line-height: 1.1; letter-spacing: 0.12em; text-align: justify; text-transform: uppercase; max-width: 120ch; }
.hero { height: 100vh; }
.hero h1 { background: linear-gradient(90deg, #8b5cf6, #6366f1); -webkit-background-clip: text; color: transparent; letter-spacing: -0.08em; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.2em; font-size: 11px; }
.card { border-left: 4px solid #8b5cf6; border-radius: 16px; box-shadow: 0 0 40px rgba(139, 92, 246, 0.6); transition: all .3s cubic-bezier(0.68, -0.55, 0.265, 1.55); }
.card:focus { outline: none; }
.glass { backdrop-filter: blur(20px); }
.glass2 { backdrop-filter: blur(12px); }
.blob { filter: blur(120px); background: radial-gradient(circle, #a855f7, transparent 70%); }
.grid-bg { background-image: linear-gradient(#ffffff10 1px, transparent 1px), linear-gradient(90deg, #ffffff10 1px, transparent 1px); background-size: 40px 40px; }
.stripes { background: repeating-linear-gradient(45deg, #111 0 10px, #222 10px 20px); }
.btn { box-shadow: 6px 6px 0 #000; }
.dot { animation: pulse 2s infinite; }
.caret { animation: blink 1s steps(1) infinite; }
.ticker { animation: marquee 20s linear infinite; }
.reveal { opacity: 0; transform: translateY(40px); }
.modal { z-index: 99999; }
@keyframes pulse { 50% { opacity: .4; } }
@keyframes blink { 50% { opacity: 0; } }
@keyframes marquee { to { transform: translateX(-50%); } }
</style>
</head>
<body>
<section class="hero">
  <span class="eyebrow">Новое поколение</span>
  <h1>Революционная платформа, которая бесшовно меняет всё</h1>
  <p>Lorem ipsum dolor sit amet... Мы делаем передовые решения мирового уровня.</p>
  <a href="#">Начать →</a> <a href="#">Узнать →</a> <a href="#">Цены →</a>
</section>
<div class="cards">
  <div class="card"><div class="icon-box">🚀</div><h3>Скорость</h3><p>Быстро</p></div>
  <div class="card"><div class="icon-box">✨</div><h3>Магия</h3><p>Красиво</p></div>
  <div class="card"><div class="icon-box">🔒</div><h3>Защита</h3><p>Надёжно</p></div>
</div>
<span>01</span><h4>Шаг</h4>
<span>02</span><h4>Шаг</h4>
<span>03</span><h4>Шаг</h4>
<img src="">
<img src="https://via.placeholder.com/600x400">
<div onclick="go()">Перейти</div>
<button><svg width="16" height="16"></svg></button>
<input type="email" name="email">
<input type="text" tabindex="3">
<video src="hero.mp4" autoplay loop></video>
<script>
window.addEventListener('wheel', function (e) { e.preventDefault(); });
</script>
</body>
</html>
"""

GOOD_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Мастерская керамики на Лиговском</title>
<style>
:root { --bg: #f7f9fa; --ink: #1f3038; --muted: #4d5b62; --accent: #0d7480; }
body { font-family: "Onest", "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--ink); font-size: 1.0625rem; line-height: 1.6; }
p { max-width: 68ch; text-wrap: pretty; }
h1 { font-size: clamp(2.5rem, 6vw, 4.5rem); line-height: 1.05; letter-spacing: -0.02em; text-wrap: balance; }
.hero { min-height: 100svh; display: grid; align-content: end; padding: 6rem 1.5rem 4rem; }
.button { background: var(--accent); color: #fff; padding: 0.875rem 1.5rem; border-radius: 10px;
  transition: background-color 160ms cubic-bezier(0.16, 1, 0.3, 1), transform 160ms cubic-bezier(0.16, 1, 0.3, 1); }
.button:hover { background: #0a5f69; }
.button:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
.photo { border-radius: 12px; box-shadow: 0 8px 24px rgba(31, 48, 56, 0.12); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
</style>
</head>
<body>
<a class="skip" href="#main">К содержанию</a>
<main id="main">
<section class="hero">
  <h1>Гончарная мастерская на Лиговском: занятия по выходным</h1>
  <p>Три часа за кругом, глина и обжиг включены. Группа до шести человек.</p>
  <a class="button" href="#booking">Записаться на субботу</a>
</section>
<section id="booking">
  <h2>Как записаться</h2>
  <img src="studio.jpg" alt="Гончарный круг у окна" width="1200" height="800" loading="lazy">
  <form>
    <label for="email">Почта</label>
    <input id="email" type="email" name="email" autocomplete="email">
    <button type="submit">Записаться</button>
    <button type="button" aria-label="Закрыть"><svg width="16" height="16" aria-hidden="true"></svg></button>
  </form>
</section>
</main>
</body>
</html>
"""

# Правила, которые обязан поймать образец «плохо».
EXPECTED_IN_BAD = {
    "gradient-text", "ai-violet-gradient", "side-stripe", "glow-shadow",
    "hard-offset-shadow", "bounce-easing", "transition-all", "outline-none",
    "no-reduced-motion", "overused-font", "caps-label", "eyebrow-class",
    "numbered-markers", "emoji-icons", "icon-tile-cards", "glass-default",
    "blur-blob", "grid-background", "repeating-stripes", "pulsing-dot",
    "blinking-cursor", "marquee", "tiny-text", "tight-leading", "wide-tracking",
    "crushed-tracking", "long-measure", "justified-text", "caps-body",
    "zoom-disabled", "img-no-alt", "img-no-size", "placeholder-image",
    "placeholder-text", "buzzwords", "three-dots", "click-div",
    "icon-button-no-label", "input-no-label", "skipped-heading", "arrow-links",
    "dark-neon", "video-autoplay", "scroll-hijack", "hidden-at-rest",
    "vh-hero", "z-index-chaos", "positive-tabindex", "identical-cards",
}


class CheckModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check = load_check()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_rules_registry_is_complete(self):
        rules = self.check.RULES
        self.assertGreaterEqual(len(rules), 25)
        ids = [r.id for r in rules]
        self.assertEqual(len(ids), len(set(ids)), "id правил повторяются")
        catalog = CATALOG.read_text(encoding="utf-8")
        anchors = set(re.findall(r"^#{2,4} .*?\{#([a-z0-9-]+)\}", catalog, re.M))
        for rule in rules:
            self.assertTrue(rule.description and rule.advice, rule.id)
            self.assertTrue(rule.ref.startswith("антипаттерны.md#"), rule.id)
            anchor = rule.ref.split("#", 1)[1]
            self.assertIn(anchor, anchors, f"{rule.id}: раздела {anchor} нет в каталоге")

    def test_bad_sample_triggers_expected_rules(self):
        path = self.write("bad.html", BAD_HTML)
        found = {f.rule for f in self.check.scan([path])}
        missing = EXPECTED_IN_BAD - found
        self.assertFalse(missing, f"не пойманы: {sorted(missing)}")

    def test_good_sample_is_clean(self):
        path = self.write("good.html", GOOD_HTML)
        findings = self.check.scan([path])
        self.assertEqual([], [(f.rule, f.line) for f in findings])

    def test_finding_points_to_real_line(self):
        path = self.write("bad.html", BAD_HTML)
        lines = BAD_HTML.splitlines()
        for f in self.check.scan([path]):
            if f.rule == "gradient-text":
                self.assertIn("background-clip", lines[f.line - 1])
                break
        else:
            self.fail("gradient-text не найден")

    def test_css_file_and_directory_walk(self):
        self.write("site/css/main.css", ".x { transition: all 1s; }\n")
        self.write("site/node_modules/lib.css", ".y { transition: all 1s; }\n")
        findings = self.check.scan([self.dir / "site"])
        rules = {(Path(f.path).name, f.rule) for f in findings}
        self.assertIn(("main.css", "transition-all"), rules)
        self.assertFalse(any(name == "lib.css" for name, _ in rules))

    def test_ignore_comment_suppresses_rule(self):
        css = "/* aidesign-ignore: hard-offset-shadow — необрутализм выбран */\n.b { box-shadow: 6px 6px 0 #000; }\n"
        path = self.write("brutal.css", css)
        self.assertNotIn("hard-offset-shadow", {f.rule for f in self.check.scan([path])})

    def rules_in(self, name, body):
        page = "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><title>t</title></head><body>\n%s\n</body></html>\n" % body
        return {f.rule for f in self.check.scan([self.write(name, page)])}

    def test_skill_placeholder_is_not_a_finding(self):
        body = "<h1>[Заголовок — впиши]</h1>\n<p>Цена: [ЦЕНА — впиши]</p>\n<p>[Название компании — впиши]</p>\n<a class=\"button\" href=\"#\">[Кнопка — впиши]</a>"
        self.assertNotIn("placeholder-text", self.rules_in("skill-placeholder.html", body))
        self.assertIn("placeholder-text", self.rules_in("raw-placeholder.html", "<p>[Название компании]</p>"))

    def test_invented_metrics(self):
        for bad in ("<p>10,000+ happy customers</p>", "<p>1000+ довольных клиентов</p>",
                    "<p>Нам доверяют 500+ клиентов</p>", "<strong>50k+</strong> <span>users</span>",
                    "<p>Более 2 000+ учеников</p>"):
            self.assertIn("invented-metrics", self.rules_in("m.html", bad), bad)
        for good in ("<p>Группа до 6 человек, 3 часа за кругом.</p>", "<p>Пишем на C++ и Python 3+</p>",
                     "<p>Возраст 18+, 1000 км трассы</p>", "<p>[Число клиентов — впиши]</p>"):
            self.assertNotIn("invented-metrics", self.rules_in("m.html", good), good)

    def test_generic_cta(self):
        for bad in ("<button>Get Started</button>", "<a class=\"btn btn-primary\" href=\"#\">Learn more</a>",
                    "<button type=\"button\"> Начать </button>", "<a class=\"button\" href=\"#\">Узнать больше →</a>",
                    "<input type=\"submit\" value=\"Get started\">"):
            self.assertIn("generic-cta", self.rules_in("c.html", bad), bad)
        for good in ("<button>Записаться на субботу</button>", "<a class=\"button\" href=\"#\">Узнать больше о глине</a>",
                     "<a href=\"/about\">Узнать больше</a>", "<button>Начать урок 3</button>"):
            self.assertNotIn("generic-cta", self.rules_in("c.html", good), good)

    def test_identical_cards(self):
        card = "<div class=\"card\"><h3>%s</h3><p>%s</p></div>"
        bad = "<div class=\"grid\">%s</div>" % "".join(card % (t, t) for t in ("Один", "Два", "Три"))
        self.assertIn("identical-cards", self.rules_in("cards.html", bad))
        two = "<div class=\"grid\">%s</div>" % "".join(card % (t, t) for t in ("Один", "Два"))
        self.assertNotIn("identical-cards", self.rules_in("cards.html", two))
        varied = ("<div class=\"grid\"><article class=\"big\"><h3>Один</h3><p>Текст</p><img src=\"a.jpg\" alt=\"\" width=\"1\" height=\"1\"></article>"
                  "<div class=\"card\"><h3>Два</h3><p>Текст</p></div>"
                  "<blockquote><p>Цитата</p></blockquote></div>")
        self.assertNotIn("identical-cards", self.rules_in("cards.html", varied))
        menu = "<ul>%s</ul>" % "".join("<li><a href=\"#\">%s</a></li>" % t for t in "абвг")
        self.assertNotIn("identical-cards", self.rules_in("cards.html", menu))
        steps = "<ol>%s</ol>" % "".join("<li><h3>%s</h3><p>%s</p></li>" % (t, t) for t in ("Шаг", "Ещё", "Итог"))
        self.assertNotIn("identical-cards", self.rules_in("cards.html", steps))

    def test_reduced_motion_from_a_neighbour_css_of_the_same_check(self):
        """Анимация в одном файле, @media (prefers-reduced-motion) — в соседнем CSS той же проверки."""
        anim = self.write("site/css/motion.css", ".x { transition: transform .3s ease; }\n")
        self.write("site/css/a11y.css", "@media (prefers-reduced-motion: reduce) { * { transition: none; } }\n")
        rules = {f.rule for f in self.check.scan([self.dir / "site"])}
        self.assertNotIn("no-reduced-motion", rules)
        alone = {f.rule for f in self.check.scan([anim])}         # без соседа — находка остаётся
        self.assertIn("no-reduced-motion", alone)

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.check.scan([self.dir / "нет-такого.html"])


class CheckCliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(CHECK), *map(str, args)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_cli_exit_codes_and_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.html"
            good = Path(tmp) / "good.html"
            bad.write_text(BAD_HTML, encoding="utf-8")
            good.write_text(GOOD_HTML, encoding="utf-8")

            res = self.run_cli(bad)
            self.assertEqual(res.returncode, 1, res.stderr)
            self.assertRegex(res.stdout, r"bad\.html:\d+ — \[[a-z-]+\] .+ — .+")
            self.assertRegex(res.stdout, r"Находок: \d+")

            res = self.run_cli(good)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("Находок: 0", res.stdout)

            res = self.run_cli(Path(tmp) / "нет.html")
            self.assertEqual(res.returncode, 2)

            res = self.run_cli()
            self.assertEqual(res.returncode, 2)

    def test_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.html"
            bad.write_text(BAD_HTML, encoding="utf-8")
            res = self.run_cli(bad, "--json")
            self.assertEqual(res.returncode, 1)
            data = json.loads(res.stdout)
            self.assertEqual(data["count"], len(data["findings"]))
            first = data["findings"][0]
            self.assertEqual(set(first), {"path", "line", "rule", "message", "fix", "ref"})


FIXTURES = ROOT / "tests" / "fixtures" / "check"
TOOLS = ROOT / "skills" / "aidesign" / "tools"
# Новые правила паритета с Impeccable (задача 14): у каждого — образцы <id>-bad.* и <id>-good.*.
NEW_STATIC = [
    "border-accent-on-rounded", "flat-type-hierarchy", "nested-cards", "monotonous-spacing",
    "italic-serif-display", "oversized-h1", "em-dash-overuse", "aphoristic-cadence", "theater-slop-phrase",
    "gray-on-color", "low-contrast", "undersized-ui-text", "cramped-padding", "repeated-container-text",
    "clipped-overflow-container", "gpt-thin-border-wide-shadow", "buried-raster", "organic-clip-path",
    "shape-assembled-illustration", "design-system-radius", "design-system-font-size",
]
NEW_BROWSER = [
    "script-error", "edge-flush-cards", "text-occlusion", "first-viewport-column-overflow",
    "body-text-viewport-edge", "heading-rhythm", "straggler", "unbalanced-heading", "text-overflow",
    "content-hidden-at-rest", "line-length",
]
# Реестр Impeccable (crates/foundation/src/registry.rs), 62 правила, в порядке источника.
IMPECCABLE = [
    "side-tab", "border-accent-on-rounded", "overused-font", "flat-type-hierarchy", "gradient-text",
    "ai-color-palette", "cream-palette", "nested-cards", "monotonous-spacing", "bounce-easing", "pulsing-dot",
    "blinking-cursor", "shape-assembled-illustration", "organic-clip-path", "buried-raster", "hard-offset-shadow",
    "dark-glow", "radial-halo", "radial-spotlight-glow", "marquee", "icon-tile-stack", "italic-serif-display",
    "hero-eyebrow-chip", "kicker-above-heading", "numbered-section-labels", "em-dash-overuse",
    "marketing-buzzword", "aphoristic-cadence", "oversized-h1", "extreme-negative-tracking", "broken-image",
    "script-error", "content-hidden-at-rest", "edge-flush-cards", "text-occlusion",
    "first-viewport-column-overflow", "gray-on-color", "low-contrast", "line-length", "cramped-padding",
    "body-text-viewport-edge", "tight-leading", "skipped-heading", "heading-rhythm", "justified-text",
    "straggler", "unbalanced-heading", "tiny-text", "undersized-ui-text", "all-caps-body", "wide-tracking",
    "text-overflow", "repeated-container-text", "clipped-overflow-container", "design-system-font",
    "design-system-color", "design-system-radius", "design-system-font-size", "gpt-thin-border-wide-shadow",
    "repeating-stripes-gradient", "codex-grid-background", "theater-slop-phrase",
]
# Ожидания по образцам Impeccable (tests/oracle/golden источника), id переведены в наши.
IMPECCABLE_FLAGS = {
    "jsx-should-flag.jsx": {"ai-violet-gradient", "bounce-easing", "gradient-text", "side-stripe"},
    "cssinjs-should-flag.tsx": {"bounce-easing", "gradient-text", "overused-font", "side-stripe"},
    "vue-should-flag.vue": {"ai-violet-gradient", "bounce-easing", "gradient-text", "overused-font", "side-stripe"},
    "svelte-should-flag.svelte": {"ai-violet-gradient", "bounce-easing", "gradient-text", "overused-font", "side-stripe"},
    "should-flag.html": {"border-accent-on-rounded", "side-stripe"},
    "typography-should-flag.html": {"flat-type-hierarchy", "overused-font"},
    "css-in-prose-should-flag.html": {"ai-violet-gradient", "gradient-text"},
}
# Правила, которые есть у Impeccable (в наших id): на образцах should-pass их быть не должно.
IMPECCABLE_SIDE = {
    "side-stripe", "border-accent-on-rounded", "overused-font", "flat-type-hierarchy", "gradient-text",
    "ai-violet-gradient", "dark-neon", "cream-terracotta", "nested-cards", "monotonous-spacing", "bounce-easing",
    "pulsing-dot", "blinking-cursor", "shape-assembled-illustration", "organic-clip-path", "buried-raster",
    "hard-offset-shadow", "glow-shadow", "blur-blob", "marquee", "icon-tile-cards", "italic-serif-display",
    "eyebrow-class", "caps-label", "numbered-markers", "em-dash-overuse", "buzzwords", "aphoristic-cadence",
    "oversized-h1", "crushed-tracking", "placeholder-image", "hidden-at-rest", "gray-on-color", "low-contrast",
    "long-measure", "cramped-padding", "tight-leading", "skipped-heading", "justified-text", "tiny-text",
    "undersized-ui-text", "caps-body", "wide-tracking", "repeated-container-text", "clipped-overflow-container",
    "gpt-thin-border-wide-shadow", "repeating-stripes", "grid-background", "theater-slop-phrase",
}


def samples(folder):
    """(путь, id правила, bad|good) для образцов <id>-{bad,good}.* в папке и подпапках."""
    out = []
    for f in sorted(folder.rglob("*")):
        m = re.fullmatch(r"(.+)-(bad|good)", f.stem)
        if f.is_file() and m and "impeccable" not in f.parts:
            out.append((f, m.group(1), m.group(2)))
    return out


class ParityStaticTest(unittest.TestCase):
    """Новые правила статикой: образцы bad ловятся, good — нет; компоненты и Tailwind понимаются."""

    @classmethod
    def setUpClass(cls):
        cls.check = load_check()

    def test_every_new_rule_has_bad_and_good_samples(self):
        have = {(rid, kind) for _, rid, kind in samples(FIXTURES) if "browser" not in _.parts}
        for rid in NEW_STATIC:
            self.assertIn((rid, "bad"), have, rid)
            self.assertIn((rid, "good"), have, rid)
            self.assertIn(rid, {r.id for r in self.check.RULES})

    def test_samples(self):
        for path, rid, kind in samples(FIXTURES):
            if "browser" in path.parts:
                continue
            with self.subTest(sample=str(path.relative_to(FIXTURES))):
                found = {f.rule for f in self.check.scan([path])}
                if kind == "bad":
                    self.assertIn(rid, found)
                else:
                    self.assertNotIn(rid, found)

    def test_light_and_dark_themes_are_checked_apart(self):
        """tokens.css с двумя темами (potter-clay справочника): цвета разных тем не складываются."""
        self.assertEqual([], [(f.rule, f.line) for f in self.check.scan([FIXTURES / "cream-terracotta-good.css"])])
        self.assertIn("cream-terracotta", {f.rule for f in self.check.scan([FIXTURES / "cream-terracotta-bad.css"])})
        self.assertIn("dark-neon", {f.rule for f in self.check.scan([FIXTURES / "dark-neon-bad.css"])})
        self.assertNotIn("dark-neon", {f.rule for f in self.check.scan([FIXTURES / "dark-neon-good.css"])})
        # Тёмная основная тема: pick.py "керамика" --dark --direction 1 --tokens (potter-clay) — светлая лишь переопределение.
        self.assertEqual([], [(f.rule, f.line) for f in self.check.scan([FIXTURES / "cream-terracotta-good-dark.css"])])
        self.assertIn("cream-terracotta", {f.rule for f in self.check.scan([FIXTURES / "cream-terracotta-bad-dark.css"])})

    def test_component_samples_exist(self):
        exts = {p.suffix for p, _, kind in samples(FIXTURES) if kind == "bad"}
        self.assertTrue({".jsx", ".vue", ".svelte"} <= exts, exts)

    def test_impeccable_flag_samples(self):
        for name, want in IMPECCABLE_FLAGS.items():
            with self.subTest(sample=name):
                found = {f.rule for f in self.check.scan([FIXTURES / "impeccable" / name])}
                self.assertFalse(want - found, "не пойманы: %s" % sorted(want - found))

    def test_impeccable_pass_samples(self):
        for path in sorted((FIXTURES / "impeccable").glob("*should-pass*")):
            with self.subTest(sample=path.name):
                found = {f.rule for f in self.check.scan([path])} & IMPECCABLE_SIDE
                self.assertEqual(set(), found)

    def test_gray_on_color_matches_impeccable_rows(self):
        path = FIXTURES / "impeccable" / "gray-on-color.html"
        lines = path.read_text(encoding="utf-8").split("\n")
        flag = {i for i, line in enumerate(lines, 1) if 'id="flag-' in line}
        found = {f.line for f in self.check.scan([path]) if f.rule == "gray-on-color"}
        self.assertEqual(flag, found)
        self.assertEqual(6, len(flag))

    def test_component_files_are_collected_and_template_code_is_not_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for name in ("a.jsx", "b.tsx", "c.vue", "d.svelte", "e.astro", "f.scss", "g.md"):
                (d / name).write_text("", encoding="utf-8")
            self.assertEqual({".jsx", ".tsx", ".vue", ".svelte", ".astro", ".scss"},
                             {p.suffix for p in self.check.collect_files([d])})
            vue = d / "card.vue"
            vue.write_text('<template>\n  <p class="lead">{{ title }}</p>\n</template>\n', encoding="utf-8")
            jsx = d / "card.jsx"
            jsx.write_text("const seamless = useState<string>(null);\nexport const C = () => (\n  <p>{seamless}</p>\n);\n",
                           encoding="utf-8")
            rules = {f.rule for f in self.check.scan([vue, jsx])}
            self.assertNotIn("placeholder-text", rules)       # {{ title }} — выражение, не заглушка
            self.assertNotIn("buzzwords", rules)              # имя переменной — код, не текст

    def test_scss_nesting_and_tailwind_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scss = Path(tmp) / "card.scss"
            scss.write_text(".card {\n  padding: 24px;\n  .title {\n    background-clip: text;\n  }\n}\n", encoding="utf-8")
            found = [f for f in self.check.scan([scss]) if f.rule == "gradient-text"]
            self.assertEqual([4], [f.line for f in found])
            page = Path(tmp) / "tw.html"
            page.write_text('<p class="tracking-tighter text-[10px]">Мелко и тесно</p>\n', encoding="utf-8")
            rules = {f.rule for f in self.check.scan([page])}
            self.assertTrue({"crushed-tracking", "tiny-text"} <= rules, rules)


class ExceptionsAndFastTest(unittest.TestCase):
    """aidesign-ignore-file, .aidesign-check.json, --fast, --hook."""

    @classmethod
    def setUpClass(cls):
        cls.check = load_check()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, "-B", str(CHECK), *map(str, args)], capture_output=True,
                              text=True, encoding="utf-8", input=stdin)

    def test_ignore_file_comment(self):
        css = "/* aidesign-ignore-file: hard-offset-shadow — необрутализм в DESIGN.md */\n.a { box-shadow: 6px 6px 0 #000; }\n.b { box-shadow: 4px 4px 0 #000; }\n"
        path = self.dir / "brutal.css"
        path.write_text(css, encoding="utf-8")
        self.assertNotIn("hard-offset-shadow", {f.rule for f in self.check.scan([path])})

    def test_project_config(self):
        site = self.dir / "site"
        (site / "demo").mkdir(parents=True)
        (site / "a.css").write_text(".a { transition: all 1s; box-shadow: 6px 6px 0 #000; }\n", encoding="utf-8")
        (site / "demo" / "b.css").write_text(".b { transition: all 1s; }\n", encoding="utf-8")
        (site / ".aidesign-check.json").write_text(
            json.dumps({"ignoreRules": ["hard-offset-shadow"], "ignoreFiles": ["demo/*.css"]}), encoding="utf-8")
        found = {(Path(f.path).name, f.rule) for f in self.check.scan([site])}
        self.assertIn(("a.css", "transition-all"), found)
        self.assertNotIn(("a.css", "hard-offset-shadow"), found)
        self.assertFalse([x for x in found if x[0] == "b.css"])
        raw = {(Path(f.path).name, f.rule) for f in self.check.scan([site], use_config=False)}
        self.assertIn(("b.css", "transition-all"), raw)
        (site / ".aidesign-check.json").write_text("{не json", encoding="utf-8")
        res = self.cli(site)
        self.assertEqual(2, res.returncode, res.stdout)
        self.assertIn(".aidesign-check.json", res.stderr)
        self.assertEqual(1, self.cli(site, "--no-config").returncode)

    def test_fast_keeps_mechanics_and_drops_taste(self):
        css = self.dir / "x.css"
        css.write_text('.a { font-family: "Inter", sans-serif; }\n.b { -webkit-background-clip: text; }\n', encoding="utf-8")
        full = {f.rule for f in self.check.scan([css])}
        fast = {f.rule for f in self.check.scan([css], fast=True)}
        self.assertIn("overused-font", full)
        self.assertNotIn("overused-font", fast)
        self.assertIn("gradient-text", fast)
        self.assertTrue(fast <= self.check.FAST)

    def test_hook(self):
        css = self.dir / "x.css"
        css.write_text(".b { -webkit-background-clip: text; }\n", encoding="utf-8")
        res = self.cli("--hook", stdin=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(css)}}))
        self.assertEqual(2, res.returncode)
        self.assertIn("[gradient-text]", res.stderr)
        self.assertEqual("", res.stdout)
        note = self.dir / "notes.md"
        note.write_text("text", encoding="utf-8")
        for payload in (json.dumps({"tool_input": {"file_path": str(note)}}), "не json", ""):
            self.assertEqual(0, self.cli("--hook", stdin=payload).returncode, payload)
        clean = self.dir / "ok.css"
        clean.write_text(".a { color: #1f2933; }\n", encoding="utf-8")
        self.assertEqual(0, self.cli("--hook", stdin=json.dumps({"tool_input": {"file_path": str(clean)}})).returncode)

    def test_rules_listing_marks_fast_and_browser(self):
        out = self.cli("--rules").stdout
        self.assertIn("[быстрое]", out)
        for rid in NEW_BROWSER + NEW_STATIC:
            self.assertIn(rid, out)


class ParityCatalogTest(unittest.TestCase):
    """Таблица соответствия в антипаттерны.md: все 62 правила Impeccable и рецепт хука."""

    def test_table_covers_every_impeccable_rule(self):
        self.assertEqual(62, len(IMPECCABLE))
        text = CATALOG.read_text(encoding="utf-8")
        table = text[text.index("{#impeccable-parity}"):]
        rows = dict(re.findall(r"^\| ([a-z0-9-]+) \| (.+?) \|", table, re.M))
        self.assertEqual(set(IMPECCABLE), set(rows) - {"Impeccable"})
        check = load_check()
        ours = {r.id for r in check.RULES} | set(NEW_BROWSER) | {"ds-hardcoded-font", "ds-hardcoded-color"}
        for imp, cell in rows.items():
            for rid in re.findall(r"`([a-z0-9-]+)`", cell):
                self.assertIn(rid, ours, "%s → %s" % (imp, rid))
        self.assertNotRegex(table, r"можно, но нет")

    def test_hook_recipe_and_browser_anchors(self):
        text = CATALOG.read_text(encoding="utf-8")
        self.assertIn('"PostToolUse"', text)
        self.assertIn("check.py\\\" --hook", text)
        self.assertIn("--fast", text)
        anchors = set(re.findall(r"\{#([a-z0-9-]+)\}", text))
        sys.path.insert(0, str(TOOLS))
        import check_browser
        for _, anchor, _, _ in check_browser.SPECS:
            self.assertIn(anchor, anchors)


class BrowserLayerTest(unittest.TestCase):
    """check.py --browser: без модуля — отказ с кодом 2; с модулем — образцы раскладки."""

    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, "-B", str(CHECK), *map(str, args)], capture_output=True,
                              text=True, encoding="utf-8", env=env, timeout=900)

    def test_without_browser_module_refuses_with_code_2(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, AIDESIGN_BROWSER_HOME=home)
            res = self.run_cli("--browser", FIXTURES / "browser" / "text-overflow-bad.html", env=env)
            self.assertEqual(2, res.returncode, res.stdout + res.stderr)
            self.assertIn("browser.py", res.stderr)
            self.assertEqual(2, self.run_cli("--browser", Path(home) / "нет.html", env=env).returncode)

    def test_layout_samples(self):
        sys.path.insert(0, str(TOOLS))
        import browser
        if not browser.ready():
            self.skipTest("браузерный модуль не поставлен (python3 browser.py ensure --yes или AIDESIGN_BROWSER_HOME)")
        res = self.run_cli("--browser", FIXTURES / "browser", "--json")
        self.assertIn(res.returncode, (0, 1), res.stderr)
        found = {(Path(f["path"]).name, f["rule"]) for f in json.loads(res.stdout)["findings"]}
        for path, rid, kind in samples(FIXTURES / "browser"):
            with self.subTest(sample=path.name):
                if kind == "bad":
                    self.assertIn((path.name, rid), found)
                else:
                    self.assertNotIn((path.name, rid), found)
        self.assertEqual(set(NEW_BROWSER), {rid for _, rid, _ in samples(FIXTURES / "browser")})

    def test_scroll_scene_text_is_hidden_only_when_it_leaves_the_reading_flow(self):
        """Сцена по прокрутке: подпись видна на своём месте и гаснет дальше. В потоке чтения — не находка;
        под inert (не прочесть и не найти) — находка, как обычное «скрыто в покое»."""
        sys.path.insert(0, str(TOOLS))
        import browser
        if not browser.ready():
            self.skipTest("браузерный модуль не поставлен (python3 browser.py ensure --yes или AIDESIGN_BROWSER_HOME)")
        body = "Глину замешиваем с вечера, утром она мягкая и послушная, а печь уже набирает жар для первого обжига."
        caps = "\n".join('<p class="cap" style="opacity:%d">Сцена %d. %s</p>' % (i == 0, i + 1, body) for i in range(3))
        page = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Сцены</title>
<style>body{margin:0;font:17px/1.55 system-ui,sans-serif;color:#f3ede4;background:#14110f}
.film{height:400vh;position:relative}.stage{position:sticky;top:0;height:100vh}
.cap{position:absolute;left:24px;right:24px;bottom:15vh;max-width:36rem;margin:0;text-wrap:pretty}</style></head>
<body><main><section class="film"><div class="stage">%s</div></section></main>
<script>const caps=[...document.querySelectorAll('.cap')], film=document.querySelector('.film');
function read(){const y=-film.getBoundingClientRect().top, seg=innerHeight;
caps.forEach((c,i)=>{const on=Math.abs(y-i*seg)<seg*0.4?1:0;c.style.opacity=on;if(%s)c.toggleAttribute('inert',!on);});}
addEventListener('scroll',read,{passive:true});read();</script></body></html>"""
        with tempfile.TemporaryDirectory() as tmp:
            pages = {}
            for name, inert in (("flow", "false"), ("inert", "true")):
                pages[name] = Path(tmp) / ("%s.html" % name)
                pages[name].write_text(page % (caps, inert), encoding="utf-8")
            res = self.run_cli("--browser", tmp, "--json")
            self.assertIn(res.returncode, (0, 1), res.stderr)
            found = {(Path(f["path"]).stem, f["rule"]) for f in json.loads(res.stdout)["findings"]}
        self.assertNotIn(("flow", "content-hidden-at-rest"), found)
        self.assertIn(("inert", "content-hidden-at-rest"), found)


if __name__ == "__main__":
    unittest.main()
