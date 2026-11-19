"""Тесты skills/aidesign/tools/media.py — генераторы и файлы медиа.

Шов — CLI отдельным процессом (как агент) во временной папке. Сеть — только локальный
http-сервер в этом же процессе; настоящих генераций и трат нет. ffmpeg — настоящий,
на коротком синтетическом ролике `testsrc`; без него соответствующие тесты пропускаются.
"""

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "skills", "aidesign")
MEDIA = os.path.join(SKILL, "tools", "media.py")
CATALOG = os.path.join(SKILL, "knowledge", "медиа", "генераторы.json")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
FFMPEG = shutil.which("ffmpeg")
PROXIES = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def head(path, n=16):
    with open(path, "rb") as f:
        return f.read(n)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="media-test-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def media(self, *args, env=None):
        e = dict(os.environ)
        for k in PROXIES:
            e.pop(k, None)
        e.update(env or {})
        r = subprocess.run([sys.executable, "-B", MEDIA] + list(args), capture_output=True, text=True,
                           encoding="utf-8", cwd=self.root, env=e, timeout=300)
        return r.returncode, r.stdout + r.stderr

    def ok(self, *args, **kw):
        code, out = self.media(*args, **kw)
        self.assertEqual(code, 0, out)
        return out

    def js(self, *args, **kw):
        return json.loads(self.ok(*args, "--json", **kw))


class Catalog(unittest.TestCase):
    def test_catalog_has_the_services_from_the_survey_and_marks_the_unchecked(self):
        cat = json.loads(read(CATALOG))
        ids = {s["id"] for s in cat["services"]}
        self.assertGreaterEqual(len(ids), 15)
        for need in ("higgsfield", "magnific", "syntx", "fal", "replicate", "huggingface", "elevenlabs", "runway",
                     "luma", "krea", "bfl", "leonardo", "recraft", "meshy", "pika", "codex-image-gen", "figma-shaders"):
            self.assertIn(need, ids)
        for s in cat["services"]:
            self.assertTrue(set(s) >= {"id", "title", "kinds", "match", "tools", "connect", "auth", "free", "docs"}, s["id"])
            self.assertTrue(set(s["tools"]) >= {"generate", "balance", "price", "wait", "download"}, s["id"])
            for p in s["match"]:
                re.compile(p)
        by = {s["id"]: s for s in cat["services"]}
        for unsure in ("syntx", "pika"):
            self.assertIs(by[unsure].get("unverified"), True, unsure)
        self.assertTrue(cat["generic"]["match"])
        text = read(CATALOG)
        self.assertNotRegex(text, r"(?i)(sk|r8|hf)_[a-z0-9]{16,}")      # только имена переменных, не ключи


class ServeTexts(unittest.TestCase):
    """Показ сайта с видео — сервером с Range: встроенный http.server Python кусками не отдаёт."""

    def test_texts_advise_a_range_server_not_python_http_server(self):
        for rel in ("knowledge/движение-и-медиа/видео-в-сайт.md", "knowledge/медиа/промпты-видео.md",
                    "phases/4-build.md", "phases/5-check.md", "knowledge/инструменты.md"):
            text = read(os.path.join(SKILL, *rel.split("/")))
            self.assertNotIn("python3 -m http.server", text, rel)
            self.assertIn("ad.py --serve-http", text, rel)
            self.assertIn("Range", text, rel)


class Detect(Tmp):
    NAMES = ["mcp__higgsfield__generate_image", "mcp__higgsfield__balance", "mcp__higgsfield__jobs_wait",
             "mcp__higgsfield__estimate_image_cost", "mcp__claude_ai_Magnific__images_generate",
             "mcp__claude_ai_Magnific__simulate_cost", "mcp__claude_ai_Magnific__creations_wait",
             "mcp__fal__run_model", "mcp__fal__get_pricing", "image_gen",
             "mcp__newgen__generate_video", "mcp__newgen__get_status",
             "mcp__gmail__create_draft", "mcp__figma__create_new_file", "Read", "WebSearch"]

    def test_detect_finds_known_generators_and_an_unknown_one_by_the_common_pattern(self):
        found = {f["id"]: f for f in self.js("detect", "--tools", ",".join(self.NAMES))}
        self.assertEqual(set(found), {"higgsfield", "magnific", "fal", "codex-image-gen", "newgen"})
        h = found["higgsfield"]
        self.assertEqual(h["server"], "higgsfield")
        self.assertEqual(h["tools"]["balance"], ["mcp__higgsfield__balance"])
        self.assertEqual(h["tools"]["wait"], ["mcp__higgsfield__jobs_wait"])
        self.assertEqual(h["tools"]["price"], ["mcp__higgsfield__estimate_image_cost"])
        self.assertIn("video", h["kinds"])
        self.assertEqual(found["magnific"]["server"], "claude_ai_Magnific")
        self.assertEqual(found["magnific"]["tools"]["price"], ["mcp__claude_ai_Magnific__simulate_cost"])
        self.assertEqual(found["fal"]["tools"]["price"], ["mcp__fal__get_pricing"])
        self.assertEqual(found["codex-image-gen"]["tools"]["generate"], ["image_gen"])
        u = found["newgen"]
        self.assertFalse(u["known"])
        self.assertEqual(u["kinds"], ["video"])
        self.assertEqual(u["tools"]["generate"], ["mcp__newgen__generate_video"])
        self.assertEqual(u["tools"]["wait"], ["mcp__newgen__get_status"])
        self.assertTrue(found["higgsfield"]["known"])

    def test_detect_reads_a_tools_file_and_says_it_in_words(self):
        write(os.path.join(self.root, "tools.txt"), "\n".join(self.NAMES) + "\n")
        out = self.ok("detect", "--tools-file", "tools.txt")
        self.assertIn("Higgsfield", out)
        self.assertIn("баланс", out)
        out = self.ok("detect", "--tools", "Read,mcp__gmail__create_draft")
        self.assertIn("не видно", out)

    def test_missing_tools_file_is_a_refusal(self):
        code, out = self.media("detect", "--tools-file", "нет-такого.txt")
        self.assertEqual(code, 1, out)
        self.assertIn("Отказ:", out)
        self.assertNotIn("Traceback", out)

    H = "mcp__cf833a6e-1b2c-4d5e-8f90-a1b2c3d4e5f6__"         # коннекторы claude.ai — имена-UUID
    M = "mcp__d1678d00-9e8f-4a7b-8c6d-5e4f3a2b1c0d__"

    def test_connectors_with_uuid_names_are_known_by_their_tools(self):
        names = [self.H + t for t in ("generate_image", "generate_video", "generate_audio", "generate_3d", "balance",
                                      "jobs_wait", "ads_studio_create", "get_preset_instructions", "models_explore")]
        names += [self.M + t for t in ("magnific_start", "images_generate", "video_generate", "audio_generate",
                                       "models3d_generate", "simulate_cost", "creations_wait", "creations_read")]
        names += ["mcp__higgsfield__balance", "mcp__higgsfield__generate_video", "mcp__higgsfield__jobs_wait"]
        found = self.js("detect", "--tools", ",".join(names))
        self.assertEqual(sorted(f["id"] for f in found), ["higgsfield", "magnific"])   # один Higgsfield, не два
        by = {f["id"]: f for f in found}
        for sid in ("higgsfield", "magnific"):
            self.assertTrue(by[sid]["known"], sid)
            self.assertTrue({"image", "video", "audio", "3d"} <= set(by[sid]["kinds"]), by[sid]["kinds"])
        self.assertEqual(by["higgsfield"]["server"], self.H[5:-2])
        self.assertEqual(by["higgsfield"]["tools"]["balance"], [self.H + "balance"])
        self.assertEqual(by["magnific"]["tools"]["price"], [self.M + "simulate_cost"])
        self.assertEqual(by["magnific"]["tools"]["wait"], [self.M + "creations_wait"])
        out = self.ok("detect", "--tools", ",".join(names))
        self.assertNotIn("неизвестный", out)

    def test_unknown_server_kinds_come_from_tool_names(self):
        u = "mcp__0a1b2c3d-0000-4000-8000-000000000000__"
        found = self.js("detect", "--tools", ",".join(u + t for t in ("generate_image", "create_video_job",
                                                                     "text_to_speech", "model3d_generate", "get_status")))
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0]["known"])
        self.assertEqual(set(found[0]["kinds"]), {"image", "video", "audio", "3d"})

    def test_figma_is_one_line_under_uuid_and_plain_name(self):
        """Образец из настоящей сессии 19.11: Figma пришла и коннектором-UUID, и сервером figma."""
        u = "mcp__216c9151-e377-4d46-9c9c-eb99893a55fd__"
        names = [u + "generate_image", u + "create_shader", u + "use_figma", "mcp__figma__generate_image",
                 "mcp__figma__create_shader", "mcp__figma__get_design_context"]
        for sample in (names, names[:3], names[3:]):
            found = self.js("detect", "--tools", ",".join(sample))
            self.assertEqual([(f["title"], f["known"]) for f in found], [("Figma", True)], sample)
            self.assertEqual(found[0]["kinds"], ["image", "shader"])
        found = self.js("detect", "--tools", u + "use_figma," + u + "get_design_context")
        self.assertEqual(found, [])                             # Figma без генерации — не генератор

    def test_figma_counts_only_with_the_shader_tool(self):
        self.assertEqual(self.js("detect", "--tools", "mcp__figma__create_new_file,mcp__figma__use_figma"), [])
        got = self.js("detect", "--tools", "mcp__plugin_figma_figma__create_shader")
        self.assertEqual([f["id"] for f in got], ["figma-shaders"])


class Connect(Tmp):
    def test_known_service_prints_the_catalog_command_and_runs_nothing(self):
        out = self.ok("connect", "higgsfield", "--host", "claude")
        self.assertIn("claude mcp add --transport http higgsfield https://mcp.higgsfield.ai/mcp", out)
        self.assertIn("/mcp", out)
        out = self.ok("connect", "fal", "--host", "codex")
        self.assertIn("codex mcp add fal --url https://mcp.fal.ai/mcp-relay", out)
        self.assertIn("codex mcp login fal", out)
        out = self.ok("connect", "replicate", "--host", "codex")
        self.assertIn("REPLICATE_API_TOKEN=<ваш токен>", out)

    def test_unknown_service_gets_the_common_template(self):
        out = self.ok("connect", "newgen", "--host", "claude", "--url", "https://mcp.newgen.example/mcp")
        self.assertIn("claude mcp add --transport http newgen https://mcp.newgen.example/mcp", out)
        out = self.ok("connect", "newgen", "--host", "codex")
        self.assertIn("codex mcp add newgen --url <URL>", out)
        self.assertIn("codex mcp login newgen", out)
        self.assertNotEqual(self.media("connect", "newgen", "--host", "cursor")[0], 0)

    def test_builtin_codex_generation_needs_no_connection(self):
        got = self.js("connect", "codex-image-gen", "--host", "codex")
        self.assertEqual(got["commands"], [])
        self.assertTrue(any("встроен" in n for n in got["notes"]))


class Skills(Tmp):
    def skill(self, rel, name, desc):
        write(os.path.join(self.root, rel, "SKILL.md"), "---\nname: %s\ndescription: %s\n---\n# %s\n" % (name, desc, name))

    def test_finds_media_and_prompt_skills_and_skips_the_rest(self):
        self.skill("a/skills/kartinki", "kartinki", "Промпты для генерации картинок в Nano Banana и Midjourney")
        self.skill("a/skills/video-loop", "video-loop", "Make seamless looping hero video with Kling")
        self.skill("b/plugins/x/1.0/skills/shaders", "shaders", "WebGL shader recipes: noise, gradients, particles")
        self.skill("a/skills/pdf", "pdf", "Работа с PDF-документами и таблицами")
        self.skill("a/skills/git-flow", "git-flow", "Ветки, коммиты и релизы")
        write(os.path.join(self.root, "a", "skills", "notes", "README.md"), "картинки и видео")
        got = self.js("skills", "--roots", os.path.join(self.root, "a"), os.path.join(self.root, "b"))
        self.assertEqual(sorted(s["name"] for s in got), ["kartinki", "shaders", "video-loop"])
        k = next(s for s in got if s["name"] == "kartinki")
        self.assertEqual(os.path.realpath(k["path"]),
                         os.path.realpath(os.path.join(self.root, "a", "skills", "kartinki", "SKILL.md")))
        self.assertIn("Nano Banana", k["about"])

    def test_one_line_per_skill_strict_choice_and_order_with_a_reason(self):
        """Срез живого компьютера 19.11: дубли по разным папкам и скиллы, где «промпт» или «видео» — просто слово."""
        for root in ("a", "b"):                                   # один скилл в двух местах
            self.skill(root + "/skills/video-prompt-builder", "video-prompt-builder",
                       "Generate detailed, shot-by-shot AI video prompts for Seedance 2.0 from a creative brief")
        self.skill("a/skills/higgsfield-generate", "higgsfield-generate",
                   "Generate images/videos/3D assets/audio via Higgsfield AI. Seedance 2.0 for video, Nano Banana for images")
        self.skill("a/skills/foto-prompty", "foto-prompty", "Промпты к нейросетям для фото: свет, объектив, кожа")
        self.skill("a/skills/pishu-v-potok", "пишу-в-поток",
                   "Тексты для закрытого потока курса: посты, объявления, промпт для ученика, видео-уроки и эфиры")
        self.skill("a/skills/telegram-personal-mcp", "telegram-personal-mcp",
                   "Personal Telegram MCP: read chats, download photos and videos, media, voice messages")
        self.skill("a/skills/learn", "learn", "Learning how something works: explanations, examples, images, "
                   "a prompt to think, video lectures")
        self.skill("a/skills/zoom-video-sdk", "zoom-video-sdk", "Zoom Video SDK for web video sessions and audio")
        self.skill("b/skills/remotion-create", "remotion-create", "Create a new Remotion video")
        got = self.js("skills", "--roots", os.path.join(self.root, "a"), os.path.join(self.root, "b"))
        names = [s["name"] for s in got]
        self.assertEqual(len(names), len(set(names)), names)
        self.assertEqual(set(names), {"video-prompt-builder", "higgsfield-generate", "foto-prompty"})
        self.assertEqual(names[0], "higgsfield-generate")                # больше признаков — выше
        for s in got:
            self.assertTrue(s.get("why"), s)
        vp = next(s for s in got if s["name"] == "video-prompt-builder")
        self.assertEqual(len(vp["paths"]), 2)
        out = self.ok("skills", "--roots", os.path.join(self.root, "a"), os.path.join(self.root, "b"))
        self.assertEqual(out.count("video-prompt-builder —"), 1, out)


class Handler(http.server.BaseHTTPRequestHandler):
    BIG = 2 * 1024 * 1024
    UNSAFE = {"/svg-script": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
              "/svg-onload": b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect/></svg>',
              "/svg-foreign": b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div>x</div></foreignObject></svg>',
              # образцы повторного ревью: префиксы, сущности, XHTML без foreignObject
              "/svg-prefix-script": b'<x:svg xmlns:x="http://www.w3.org/2000/svg"><x:script>alert(1)</x:script></x:svg>',
              "/svg-prefix-onload": b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/2000/svg" '
                                    b'x:onload="alert(1)"><rect/></svg>',
              "/svg-entity-href": b'<svg xmlns="http://www.w3.org/2000/svg"><a href="java&#115;cript:alert(1)">'
                                  b'<rect width="9" height="9"/></a></svg>',
              "/svg-entity-use": b'<svg xmlns="http://www.w3.org/2000/svg"><use href="java&#115;cript:alert(1)"/></svg>',
              "/svg-xhtml-iframe": b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:h="http://www.w3.org/1999/xhtml">'
                                   b'<h:iframe src="https://example.com"/></svg>',
              "/svg-external-use": b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
                                   b'<use xlink:href="https://example.com/s.svg#a"/></svg>',
              "/svg-doctype": b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg">'
                              b'<text>&x;</text></svg>',
              "/svg-style-import": b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(https://e.com/a.css);</style></svg>',
              "/svg-broken": b'<svg xmlns="http://www.w3.org/2000/svg"><rect></svg>'}
    # MP3: два кадра MPEG-1 Layer III 128 кбит/с 44,1 кГц; длина кадра 144*128000/44100 = 417 байт (вручную)
    FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413
    GOOD = {"/mp3": FRAME * 3,
            "/mp3-id3": b"ID3\x04\x00\x00\x00\x00\x00\x14" + b"\x00" * 20 + FRAME * 3,    # тег 20 байт, синхробезопасно
            "/svg-rich": b'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
                         b'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10"><defs><linearGradient id="g">'
                         b'<stop offset="0" stop-color="#fff"/></linearGradient><symbol id="s"><circle r="2"/></symbol></defs>'
                         b'<style>.a{fill:url(#g)}</style><use xlink:href="#s"/><image href="data:image/png;base64,iVBORw0KGgo="/>'
                         b'<path class="a" d="M0 0h10v10z"/></svg>'}
    FAKE_MP3 = {"/fake-mp3": b"\xff\xfb<html><body>not found</body></html>",
                "/fake-mp3-space": b"\xff\xfb <html><body>not found</body></html>" + b" " * 600,
                "/fake-mp3-http": b"\xff\xfbHTTP error 404: not found" + b" " * 600,
                "/fake-id3": b"ID3\x03<html><body>not found</body></html>" + b" " * 600}

    def log_message(self, *a):
        pass

    def send(self, body, length=True, ctype="application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if length:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):          # клиент бросил на лимите — так и задумано
            pass

    def do_GET(self):
        p = self.path
        if p == "/img":
            self.send(PNG, ctype="image/png")
        elif p == "/svg":
            self.send(b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        elif p == "/page":
            self.send(b"<!doctype html><html><body>expired</body></html>", ctype="image/png")
        elif p == "/big":
            self.send(PNG + b"\x00" * self.BIG)
        elif p == "/big-nolength":
            self.send(PNG + b"\x00" * self.BIG, length=False)
            self.close_connection = True
        elif p == "/to-file":
            self.send_response(302)
            self.send_header("Location", "file:///etc/hosts")
            self.end_headers()
        elif p in self.UNSAFE:
            self.send(self.UNSAFE[p], ctype="image/svg+xml")
        elif p in self.FAKE_MP3:
            self.send(self.FAKE_MP3[p], ctype="audio/mpeg")
        elif p in self.GOOD:
            self.send(self.GOOD[p])
        elif p == "/to-img":
            self.send_response(302)
            self.send_header("Location", "/img")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class Fetch(Tmp):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def files(self, *parts):
        out = []
        for b, _, ns in os.walk(os.path.join(self.root, *parts)):
            out += [os.path.relpath(os.path.join(b, n), self.root) for n in ns]
        return sorted(out)

    def test_downloads_into_the_project_with_type_by_first_bytes(self):
        got = self.js("fetch", "--url", self.base + "/img", "--out", "assets/media/hero")
        self.assertEqual(got["kind"], "image")
        self.assertEqual(got["format"], "png")
        self.assertEqual(self.files("assets"), [os.path.join("assets", "media", "hero.png")])
        self.assertEqual(head(os.path.join(self.root, "assets", "media", "hero.png"), 8), PNG[:8])
        got = self.js("fetch", "--url", self.base + "/svg", "--out", "assets/icon.svg")
        self.assertEqual(got["format"], "svg")
        got = self.js("fetch", "--url", self.base + "/to-img", "--out", "assets/r.png")
        self.assertEqual(got["format"], "png")

    def test_refuses_unknown_type_size_and_leaves_no_trace(self):
        for path, extra in (("/page", []), ("/big", ["--limit-mb", "1"]), ("/big-nolength", ["--limit-mb", "1"]),
                            ("/missing", [])):
            code, out = self.media("fetch", "--url", self.base + path, "--out", "assets/x.png", *extra)
            self.assertEqual(code, 1, path + ": " + out)
            self.assertEqual(self.files("assets"), [], path)

    def test_only_http_and_https_even_after_a_redirect(self):
        code, out = self.media("fetch", "--url", "file:///etc/hosts", "--out", "assets/x.png")
        self.assertEqual(code, 2, out)
        code, out = self.media("fetch", "--url", "ftp://example.com/x.png", "--out", "assets/x.png")
        self.assertEqual(code, 2, out)
        code, out = self.media("fetch", "--url", self.base + "/to-file", "--out", "assets/x.png")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.files("assets"), [])

    def test_existing_file_is_never_overwritten(self):
        mine = os.path.join(self.root, "assets", "hero.png")
        write(mine, "фото человека")
        got = self.js("fetch", "--url", self.base + "/img", "--out", "assets/hero.png")
        self.assertEqual(got["file"], "assets/hero-2.png")
        self.assertEqual(read(mine), "фото человека")
        got = self.js("fetch", "--url", self.base + "/img", "--out", "assets/hero.png")
        self.assertEqual(got["file"], "assets/hero-3.png")
        self.assertEqual(head(os.path.join(self.root, "assets", "hero-2.png"), 8), PNG[:8])

    def test_unsafe_svg_and_fake_mp3_are_refused(self):
        for path in list(Handler.UNSAFE) + list(Handler.FAKE_MP3):
            code, out = self.media("fetch", "--url", self.base + path, "--out", "assets/x")
            self.assertEqual(code, 1, path + ": " + out)
            if path in Handler.UNSAFE and path != "/svg-broken":
                self.assertIn("небезопасный SVG", out)
            self.assertEqual(self.files("assets"), [], path)

    def test_real_mp3_and_clean_svg_pass(self):
        for path, fmt in (("/mp3", "mp3"), ("/mp3-id3", "mp3"), ("/svg-rich", "svg")):
            got = self.js("fetch", "--url", self.base + path, "--out", "assets/ok" + path.replace("/", "-"))
            self.assertEqual(got["format"], fmt, path)

    def test_extension_follows_the_real_format(self):
        got = self.js("fetch", "--url", self.base + "/img", "--out", "assets/clip.mp4")
        self.assertEqual((got["file"], got["format"]), ("assets/clip.png", "png"))
        self.assertTrue(got["notes"])
        self.assertEqual(self.files("assets"), [os.path.join("assets", "clip.png")])

    def test_path_stays_inside_the_project_and_links_are_not_written_through(self):
        outside = os.path.realpath(tempfile.mkdtemp(prefix="media-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        code, out = self.media("fetch", "--url", self.base + "/img", "--out", "../escape.png")
        self.assertEqual(code, 1, out)
        code, out = self.media("fetch", "--url", self.base + "/img", "--out", os.path.join(outside, "abs.png"))
        self.assertEqual(code, 1, out)
        os.symlink(outside, os.path.join(self.root, "assets"))
        code, out = self.media("fetch", "--url", self.base + "/img", "--out", "assets/hero.png")
        self.assertEqual(code, 1, out)
        os.makedirs(os.path.join(self.root, "media"))
        os.symlink(os.path.join(outside, "target.png"), os.path.join(self.root, "media", "hero.png"))
        code, out = self.media("fetch", "--url", self.base + "/img", "--out", "media/hero.png")
        self.assertEqual(code, 1, out)
        self.assertEqual(os.listdir(outside), [])


def encoders():
    if not FFMPEG:
        return set()
    r = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True)
    return set(re.findall(r"^\s*[VAS][\w.]{5}\s+(\S+)", r.stdout, re.M))


def synth(args, out):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin"] + args + [out], check=True)


@unittest.skipUnless(FFMPEG, "ffmpeg не установлен")
class Prep(Tmp):
    def test_image_gets_webp_and_avif_widths_not_larger_than_the_source(self):
        enc = encoders()
        if not ({"libaom-av1", "libsvtav1", "librav1e"} & enc) or not ("libwebp" in enc or shutil.which("cwebp")):
            self.skipTest("нет кодировщиков AVIF или WebP")
        src = os.path.join(self.root, "hero.png")
        synth(["-f", "lavfi", "-i", "testsrc=size=1000x600:rate=1", "-frames:v", "1"], src)
        got = self.js("prep", "image", "--in", "hero.png", "--out", "assets/media")
        made = {(v["format"], v["width"]) for v in got["variants"]}
        self.assertEqual(made, {("webp", 640), ("webp", 1000), ("avif", 640), ("avif", 1000)})
        for v in got["variants"]:
            b = head(os.path.join(self.root, v["file"]), 12)
            if v["format"] == "webp":
                self.assertEqual((b[:4], b[8:12]), (b"RIFF", b"WEBP"), v)
            else:
                self.assertEqual((b[4:8], b[8:12]), (b"ftyp", b"avif"), v)

    def test_video_gets_mp4_webm_and_poster_without_sound(self):
        enc = encoders()
        if not {"libx264", "libvpx-vp9"} <= enc:
            self.skipTest("нет libx264 или libvpx-vp9")
        src = os.path.join(self.root, "loop.mov")
        synth(["-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2", "-f", "lavfi", "-i",
               "sine=frequency=440:duration=2", "-shortest", "-c:v", "mjpeg", "-c:a", "pcm_s16le"], src)
        got = self.js("prep", "video", "--in", "loop.mov", "--out", "assets/media")
        fmt = {v["format"]: os.path.join(self.root, v["file"]) for v in got["variants"]}
        self.assertTrue({"mp4", "webm", "jpg"} <= set(fmt), got)
        with open(fmt["mp4"], "rb") as f:
            data = f.read()
        self.assertEqual(data[4:8], b"ftyp")
        self.assertLess(data.index(b"moov"), data.index(b"mdat"))         # +faststart: опись ролика впереди
        self.assertEqual(head(fmt["webm"], 4), b"\x1a\x45\xdf\xa3")
        self.assertEqual(head(fmt["jpg"], 3), b"\xff\xd8\xff")
        probe = shutil.which("ffprobe")
        if probe:
            r = subprocess.run([probe, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json",
                                fmt["mp4"]], capture_output=True, text=True)
            streams = json.loads(r.stdout)["streams"]
            self.assertEqual([s["codec_type"] for s in streams], ["video"])
            self.assertEqual(streams[0]["codec_name"], "h264")

    def test_second_prep_and_a_source_in_the_out_folder_are_not_overwritten(self):
        enc = encoders()
        if not {"libx264", "libvpx-vp9"} <= enc:
            self.skipTest("нет libx264 или libvpx-vp9")
        src = os.path.join(self.root, "assets", "media", "loop.mp4")
        os.makedirs(os.path.dirname(src))
        synth(["-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=1", "-c:v", "mjpeg", "-f", "mov"], src)
        before = head(src, 1 << 20)
        first = self.js("prep", "video", "--in", "assets/media/loop.mp4", "--out", "assets/media")
        files = [v["file"] for v in first["variants"]]
        self.assertNotIn("assets/media/loop.mp4", files)
        self.assertIn("assets/media/loop-2.mp4", files)
        self.assertEqual(head(src, 1 << 20), before)                       # исходник цел
        poster = os.path.join(self.root, "assets", "media", "loop-poster.jpg")
        kept = head(poster, 1 << 20)
        second = self.js("prep", "video", "--in", "assets/media/loop.mp4", "--out", "assets/media")
        self.assertIn("assets/media/loop-poster-2.jpg", [v["file"] for v in second["variants"]])
        self.assertEqual(head(poster, 1 << 20), kept)

    def test_webp_skip_note_names_the_setup_command(self):
        if "libwebp" in encoders():
            self.skipTest("в ffmpeg есть libwebp — пропуска не будет")
        only = tempfile.mkdtemp(prefix="media-path-")
        self.addCleanup(shutil.rmtree, only, True)
        os.symlink(FFMPEG, os.path.join(only, "ffmpeg"))
        synth(["-f", "lavfi", "-i", "testsrc=size=200x100:rate=1", "-frames:v", "1"], os.path.join(self.root, "a.png"))
        got = self.js("prep", "image", "--in", "a.png", "--out", "assets", env={"AIDESIGN_MEDIA_PATH": only})
        self.assertTrue(any("setup.py install webp" in n for n in got["notes"]), got)

    def test_without_ffmpeg_code_2_and_a_hint(self):
        empty = tempfile.mkdtemp(prefix="media-path-")
        self.addCleanup(shutil.rmtree, empty, True)
        write(os.path.join(self.root, "a.png"), "x")
        code, out = self.media("prep", "image", "--in", "a.png", "--out", "assets", env={"AIDESIGN_MEDIA_PATH": empty})
        self.assertEqual(code, 2, out)
        self.assertIn("setup.py", out)


class Inventory(Tmp):
    def test_record_and_list_keep_assets_media_json(self):
        write(os.path.join(self.root, "assets", "media", "hero.png"), "x")
        self.ok("record", "--slot", "hero", "--file", "assets/media/hero.png", "--source", "higgsfield",
                "--prompt", "тёплый свет, зал", "--model", "nano_banana_pro", "--alt", "Зал студии утром")
        self.ok("record", "--slot", "bg", "--file", "", "--source", "placeholder", "--alt", "фон 16:9")
        self.ok("record", "--slot", "hero", "--file", "assets/media/hero.png", "--source", "own", "--alt", "Зал")
        data = json.loads(read(os.path.join(self.root, "assets", "media.json")))
        items = {i["slot"]: i for i in data["items"]}
        self.assertEqual(set(items), {"hero", "bg"})
        self.assertEqual(items["hero"]["source"], "own")
        self.assertEqual(items["hero"]["kind"], "image")
        self.assertRegex(items["hero"]["at"], r"T\d\d:\d\d:\d\d")
        self.assertEqual(items["bg"]["source"], "placeholder")
        listed = self.js("list")
        self.assertEqual(sorted(i["slot"] for i in listed["items"]), ["bg", "hero"])
        self.assertIn("hero", self.ok("list"))
        self.assertNotEqual(self.media("record", "--slot", "x", "--file", "a", "--source", "свои фото")[0], 0)

    def test_missing_file_and_unknown_source_are_refused(self):
        write(os.path.join(self.root, "assets", "media", "hero.png"), "x")
        self.ok("record", "--slot", "hero", "--file", "assets/media/hero.png", "--source", "own")
        before = read(os.path.join(self.root, "assets", "media.json"))
        for args in (("--file", "assets/media/нет-такого.webp", "--source", "own"),
                     ("--file", "assets/media/hero.png", "--source", "stolen")):
            code, out = self.media("record", "--slot", "bg", *args)
            self.assertEqual(code, 1, out)
            self.assertIn("Отказ:", out)
        self.assertEqual(read(os.path.join(self.root, "assets", "media.json")), before)
        self.ok("record", "--slot", "bg", "--file", "assets/media/hero.png", "--source", "magnific")

    def test_record_updates_now_in_the_project_rules(self):
        """Копии рядом с ad.py, как после init: запись в опись переписывает «Сейчас» блока aidesign."""
        work = os.path.join(self.root, ".aidesign-work")
        os.makedirs(work)
        shutil.copy(os.path.join(SKILL, "tools", "ad.py"), work)
        env = dict(os.environ, AIDESIGN_NO_UPDATE_CHECK="1")
        r = subprocess.run([sys.executable, "-B", os.path.join(work, "ad.py"), "init", "--slug", "s", "--title", "T",
                            "--skill-dir", SKILL, "--no-serve"], capture_output=True, text=True, encoding="utf-8",
                           cwd=self.root, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        write(os.path.join(self.root, "assets", "media", "hero.png"), "x")
        r = subprocess.run([sys.executable, "-B", os.path.join(work, "media.py"), "record", "--slot", "hero", "--file",
                            "assets/media/hero.png", "--source", "own"], capture_output=True, text=True,
                           encoding="utf-8", cwd=self.root, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rules = read(os.path.join(self.root, "AGENTS.md"))
        self.assertIn("мест в описи: 1", rules)
        self.assertIn("опись медиа", rules)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "права папок POSIX, не root")
    def test_os_errors_are_a_refusal_not_a_traceback(self):
        folder = os.path.join(self.root, "assets")
        os.makedirs(folder)
        os.chmod(folder, 0o500)
        try:
            code, out = self.media("record", "--slot", "hero", "--file", "", "--source", "placeholder")
        finally:
            os.chmod(folder, 0o755)
        self.assertEqual(code, 1, out)
        self.assertIn("Отказ:", out)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
