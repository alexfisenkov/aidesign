"""Тесты skills/aidesign/tools/designsystem.py — дизайн-системы проекта.

Маленькие фикстуры во временной папке: tokens.json из tokens.css по префиксам и
тёмной теме; находки «стиль мимо токенов» в формате check.py; архив.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(os.path.dirname(HERE), "skills", "aidesign", "tools", "designsystem.py")

TOKENS = """/* Токены проекта */
:root {
  --color-bg: #faf7f2;
  --color-ink: #1d1b19;
  --color-accent: #b4532a;
  --font-display: "Fraunces", Georgia, serif;
  --space-m: 24px;
  --radius-card: 14px;
  --shadow-card: 0 8px 24px rgba(0, 0, 0, .08);
  --motion-fast: 160ms;
  --measure: 68ch;
  --color-unused: #00ff00;
}
[data-theme="dark"] {
  --color-bg: #121110;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) { --color-ink: #f1ece4; }
}
"""

SITE_CSS = """body { background: var(--color-bg); color: var(--color-ink); font-family: var(--font-display); }
.card { border-radius: var(--radius-card); box-shadow: var(--shadow-card); padding: var(--space-m); max-width: var(--measure); }
a { color: var(--color-accent); transition: color var(--motion-fast); }
.cta { background: #ff3366; }
.lead { font-family: "Inter", sans-serif; }
.ok { color: transparent; border-color: currentColor; }
.miss { color: var(--color-missing); }
/* aidesign-ignore: ds-hardcoded-color — цвет логотипа партнёра */
.partner { color: rgb(10, 20, 30); }
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="ds-test-")          # родитель: туда ложится архив
        self.root = os.path.join(self.base, "проект")
        write(os.path.join(self.root, "design-system", "tokens.css"), TOKENS)
        write(os.path.join(self.root, "design-system", "styleguide.html"),
              "<style>.s{color:#123456;background:var(--color-unused)}</style>")
        write(os.path.join(self.root, "assets", "css", "site.css"), SITE_CSS)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def ds(self, *args):
        r = subprocess.run([sys.executable, "-B", DS] + list(args), capture_output=True, text=True,
                           encoding="utf-8", cwd=self.root, timeout=60)
        return r.returncode, r.stdout + r.stderr


class Export(Base):
    def test_tokens_json_by_prefix_and_dark_theme(self):
        code, out = self.ds("export", "--root", self.root)
        self.assertEqual(code, 0, out)
        with open(os.path.join(self.root, "design-system", "tokens.json"), encoding="utf-8") as f:
            t = json.load(f)
        self.assertEqual(t["color"]["bg"], "#faf7f2")
        self.assertEqual(t["color"]["accent"], "#b4532a")
        self.assertEqual(t["font"]["display"], '"Fraunces", Georgia, serif')
        self.assertEqual(t["space"]["m"], "24px")
        self.assertEqual(t["radius"]["card"], "14px")
        self.assertEqual(t["shadow"]["card"], "0 8px 24px rgba(0, 0, 0, .08)")
        self.assertEqual(t["motion"]["fast"], "160ms")
        self.assertEqual(t["other"]["measure"], "68ch")
        self.assertEqual(t["$themes"]["dark"]["color"], {"bg": "#121110", "ink": "#f1ece4"})

    def test_missing_tokens_css_is_an_input_error(self):
        os.remove(os.path.join(self.root, "design-system", "tokens.css"))
        self.assertEqual(self.ds("export", "--root", self.root)[0], 2)


class Check(Base):
    def findings(self):
        code, out = self.ds("check", os.path.join(self.root, "assets"), "--ds",
                            os.path.join(self.root, "design-system"), "--json")
        self.assertEqual(code, 1, out)
        data = json.loads(out)
        self.assertEqual(data["count"], len(data["findings"]))
        return data["findings"]

    def test_rules_find_what_goes_around_tokens(self):
        got = {(f["rule"], os.path.basename(f["path"]), f["line"]) for f in self.findings()}
        self.assertIn(("ds-hardcoded-color", "site.css", 4), got)
        self.assertIn(("ds-hardcoded-font", "site.css", 5), got)
        self.assertIn(("ds-undefined-var", "site.css", 7), got)
        self.assertIn(("ds-unused-token", "tokens.css", 12), got)
        self.assertEqual(len(got), 4, got)                     # transparent/currentColor и ignore — не находки

    def test_modern_color_functions_and_named_colors_go_around_tokens_too(self):
        """CSS Color 4: oklch, oklab, lab, lch, hwb, color() и названия цветов — тоже цвет мимо токенов."""
        write(os.path.join(self.root, "assets", "css", "site.css"),
              ".a { color: oklch(62% 0.19 30); }\n"                       # 1
              ".b { color: oklab(0.6 0.1 0.05); }\n"                      # 2
              ".c { background: lab(52% 40 30); }\n"                      # 3
              ".d { border-color: lch(52% 50 40); }\n"                    # 4
              ".e { color: hwb(12 20% 10%); }\n"                          # 5
              ".f { color: color(display-p3 1 0.4 0.2); }\n"              # 6
              ".g { color: red; }\n"                                      # 7
              ".h { border: 1px solid White; }\n"                         # 8
              ".i { color: var(--color-ink); background: var(--color-bg); }\n"
              ".j { color: transparent; border-color: currentColor; outline-color: inherit; }\n"
              ".k { content: \"red\"; animation: fade 1s; grid-area: main; }\n"
              ".l { color: var(--color-red, var(--color-accent)); font-family: var(--font-display); }\n"
              ".m { padding: var(--space-m); border-radius: var(--radius-card); box-shadow: var(--shadow-card); }\n"
              ".n { max-width: var(--measure); transition: color var(--motion-fast); }\n"
              ".o { color: var(--color-unused); }\n")
        got = {(f["rule"], f["line"]) for f in self.findings() if f["rule"] != "ds-undefined-var"}
        self.assertEqual(got, {("ds-hardcoded-color", n) for n in range(1, 9)})

    def test_findings_have_check_py_fields(self):
        for f in self.findings():
            self.assertEqual(set(f), {"path", "line", "rule", "message", "fix", "ref"})
            self.assertTrue(f["message"] and f["fix"])

    def test_text_output_like_check_py(self):
        code, out = self.ds("check", os.path.join(self.root, "assets"), "--ds", os.path.join(self.root, "design-system"))
        self.assertEqual(code, 1)
        self.assertRegex(out, r"site\.css:4 — \[ds-hardcoded-color\] .+ — .+")
        self.assertIn("Находок: 4", out)

    def test_clean_site_gives_code_0(self):
        write(os.path.join(self.root, "assets", "css", "site.css"),
              SITE_CSS.split(".cta")[0] + "i { color: var(--color-unused); }\n")
        code, out = self.ds("check", os.path.join(self.root, "assets"), "--ds", os.path.join(self.root, "design-system"))
        self.assertEqual(code, 0, out)
        self.assertIn("Находок: 0", out)


class Pack(Base):
    def zips(self):
        return sorted(n for n in os.listdir(self.base) if n.endswith(".zip"))

    def test_zip_lies_next_to_the_project_with_design_system_and_design_md(self):
        write(os.path.join(self.root, "DESIGN.md"), "# Правила\n")
        code, out = self.ds("pack", "--root", self.root, "--slug", "studio")
        self.assertEqual(code, 0, out)
        self.assertEqual([n for n in os.listdir(self.root) if n.endswith(".zip")], [])
        zips = self.zips()
        self.assertEqual(len(zips), 1)
        self.assertRegex(zips[0], r"^design-system-studio-\d{4}-\d{2}-\d{2}\.zip$")
        with zipfile.ZipFile(os.path.join(self.base, zips[0])) as z:
            names = set(z.namelist())
        self.assertIn("DESIGN.md", names)
        self.assertIn("design-system/tokens.css", names)
        self.assertIn("design-system/tokens.json", names)

    def test_existing_archive_is_not_overwritten(self):
        write(os.path.join(self.root, "DESIGN.md"), "# Правила\n")
        self.assertEqual(self.ds("pack", "--root", self.root, "--slug", "studio")[0], 0)
        first = os.path.join(self.base, self.zips()[0])
        with open(first, "rb") as f:
            before = f.read()
        self.assertEqual(self.ds("pack", "--root", self.root, "--slug", "studio")[0], 0)
        self.assertEqual(self.ds("pack", "--root", self.root, "--slug", "studio")[0], 0)
        zips = self.zips()
        self.assertEqual(len(zips), 3, zips)
        self.assertTrue(any(z.endswith("-2.zip") for z in zips) and any(z.endswith("-3.zip") for z in zips), zips)
        with open(first, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_without_design_md_refuses(self):
        self.assertEqual(self.ds("pack", "--root", self.root, "--slug", "studio")[0], 1)


if __name__ == "__main__":
    unittest.main()
