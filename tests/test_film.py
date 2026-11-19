"""Тесты skills/aidesign/tools/film.py — конвейера «сайт как фильм».

Шов — функции модуля и командная строка. Генераций нет: ролики синтетические, их делает ffmpeg
(`testsrc`, свой оттенок на сцену). Живой класс открывает страницу в настоящем браузере — по http
(сервер с Range из `ad.py --serve-http`), без Range (тогда включается Blob) и по `file://`, на
компьютере и на телефоне 390×844; пропускается, если браузерный модуль не поставлен.
"""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "skills", "aidesign")
TOOLS = os.path.join(SKILL, "tools")
FILM = os.path.join(TOOLS, "film.py")
AD = os.path.join(TOOLS, "ad.py")
CATALOG = os.path.join(SKILL, "knowledge", "медиа", "генераторы.json")
KNOW = os.path.join(SKILL, "knowledge", "медиа", "сайт-как-фильм.md")
HAS_FF = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod                     # модулю (например, check.py) нужен sys.modules[__name__]
    spec.loader.exec_module(mod)
    return mod


film = load("aidesign_film", FILM)


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def cli(*args):
    return subprocess.run([sys.executable, FILM] + list(args), capture_output=True, text=True, encoding="utf-8")


def catalog_with(tmp, models_by_service):
    with open(CATALOG, encoding="utf-8") as f:
        cat = json.load(f)
    for s in cat["services"]:
        s["models"] = models_by_service.get(s["id"], [])
    path = os.path.join(tmp, "генераторы.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False)
    return path


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="film-plan-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_plan_has_five_to_seven_beats_only(self):
        for n in (4, 8):
            self.assertEqual(cli("plan", "--beats", str(n), "--camera", "fly", "--out", self.tmp).returncode, 2, n)
        for n in (5, 6, 7):
            p = film.plan(n, "walk")
            self.assertEqual(len(p["beats"]), n)

    def test_camera_style_is_one_of_three(self):
        self.assertEqual(cli("plan", "--beats", "6", "--camera", "orbit", "--out", self.tmp).returncode, 2)
        for cam in ("fly", "walk", "locked"):
            self.assertEqual(film.plan(6, cam)["camera"], cam)

    def test_plan_writes_md_and_json_and_does_not_overwrite(self):
        r = cli("plan", "--beats", "6", "--camera", "fly", "--services", "higgsfield", "--out", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        md = read(os.path.join(self.tmp, "film-plan.md"))
        data = json.loads(read(os.path.join(self.tmp, "film-plan.json")))
        self.assertIn("Пробный кадр", md)                          # пробный кадр — до всей генерации
        self.assertIn("— впиши]", md)                              # тексты — видимые заглушки
        self.assertEqual(len(data["connectors"]), 5)
        self.assertEqual(data["seams"], "links")
        r = cli("plan", "--beats", "6", "--camera", "fly", "--out", self.tmp)
        self.assertEqual(r.returncode, 1)


class Estimate(unittest.TestCase):
    """Формула спецификации: N кадров + (2N−1) видео [×2 с телефоном] + ~15 %."""

    def test_fly_with_links_is_n_stills_and_2n_minus_1_videos(self):
        c = film.counts(6, "fly", "links", False)
        self.assertEqual((c["stills"], c["videos"]), (6, 11))
        e = film.estimate(c, 10, 50, unit="кредиты")
        self.assertEqual(e["base"], 610)                           # 6×10 + 11×50
        self.assertEqual(e["total"], 701.5)                        # +15 %
        self.assertEqual(e["probe"], 60)                           # пробный кадр и ролик
        self.assertIn("media check --amount 701.5 --unit кредиты", e["check"])

    def test_mobile_doubles_the_videos(self):
        e = film.estimate(film.counts(6, "fly", "links", True), 10, 50)
        self.assertEqual(e["base"], 1160)                          # 6×10 + 22×50

    def test_walk_has_no_links(self):
        c = film.counts(5, "walk", "chain", False)
        self.assertEqual(c["videos"], 5)
        self.assertEqual(film.estimate(c, 10, 50)["base"], 300)

    def test_without_prices_it_asks_for_a_probe_first(self):
        r = cli("estimate", "--beats", "6", "--camera", "fly", "--unit", "кредиты")
        self.assertEqual(r.returncode, 1)
        self.assertIn("пробный кадр", r.stdout)
        r = cli("estimate", "--beats", "6", "--camera", "fly", "--image-cost", "10", "--video-cost", "50",
                "--unit", "кредиты", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["total"], 701.5)

    def test_the_estimate_cannot_be_talked_down(self):
        base = ["estimate", "--camera", "fly", "--unit", "кредиты"]
        bad = [["--beats", "6", "--image-cost", "-1", "--video-cost", "10", "--link-cost", "0", "--reserve", "-0.5"],
               ["--beats", "6", "--image-cost", "10", "--video-cost", "50", "--reserve", "0.1"],
               ["--beats", "6", "--image-cost", "0", "--video-cost", "50"],
               ["--beats", "6", "--image-cost", "10", "--video-cost", "0"],
               ["--beats", "6", "--image-cost", "10", "--video-cost", "50", "--link-cost", "-1"],
               ["--beats", "4", "--image-cost", "10", "--video-cost", "50"],
               ["--beats", "8", "--image-cost", "10", "--video-cost", "50"]]
        for extra in bad:
            r = cli(*(base + extra))
            self.assertEqual(r.returncode, 2, (extra, r.stdout))
        r = cli(*(base + ["--beats", "6", "--image-cost", "10", "--video-cost", "50", "--link-cost", "0", "--json"]))
        self.assertEqual(json.loads(r.stdout)["total"], 414.0)        # (6×10 + 6×50) × 1,15 — связки бесплатны

    def test_plan_estimate_is_recounted_from_the_plan_itself(self):
        tmp = tempfile.mkdtemp(prefix="film-est-")
        self.addCleanup(shutil.rmtree, tmp)
        p = film.plan(6, "fly", mobile=True)
        p["counts"] = {"stills": 1, "clips": 1, "links": 0, "videos": 1, "mobile": False}   # подделка чисел
        path = os.path.join(tmp, "film-plan.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        r = cli("estimate", "--plan", path, "--image-cost", "10", "--video-cost", "50", "--unit", "кредиты", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["base"], 1160)          # 6×10 + 22×50 по сценам, связкам, телефону

    def test_phone_posters_are_frames_of_phone_clips_not_new_stills(self):
        p = film.plan(6, "walk", mobile=True)
        self.assertEqual(p["counts"]["stills"], 6)                     # кадров N, а не 2N
        self.assertIn("frames film/b1-m.mp4 --first", film.plan_md(p))
        self.assertIn("кадров N, а не 2N", read(KNOW))


class Models(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="film-models-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_catalog_marks_frames_on_every_model(self):
        with open(CATALOG, encoding="utf-8") as f:
            cat = json.load(f)
        found = [m for s in cat["services"] for m in s.get("models", [])]
        self.assertTrue(found)
        for m in found:
            self.assertIn(m["frames"], ("start", "start_end", "none"), m)
        self.assertTrue(any(m["frames"] == "start_end" for m in found))

    def test_start_end_model_gives_links(self):
        cat = catalog_with(self.tmp, {"luma": [{"id": "x", "title": "X", "frames": "start_end"}]})
        r = cli("models", "--services", "luma", "--camera", "fly", "--catalog", cat, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["seams"], "links")

    def test_without_end_frame_the_seams_blend_and_it_says_so(self):
        cat = catalog_with(self.tmp, {"runway": [{"id": "y", "title": "Y", "frames": "start"}]})
        r = cli("models", "--services", "runway", "--camera", "fly", "--catalog", cat)
        self.assertEqual(r.returncode, 1)
        self.assertIn("перетекание", r.stdout)
        p = film.plan(5, "fly", services=["runway"], catalog_file=cat)
        self.assertEqual(p["connectors"], [None] * 4)                # связки — null, стыки перетеканием
        self.assertEqual(p["counts"]["videos"], 5)

    def test_no_frames_at_all_is_said_honestly(self):
        cat = catalog_with(self.tmp, {"luma": [{"id": "z", "title": "Z", "frames": "none"}]})
        p = film.plan(5, "walk", services=["luma"], catalog_file=cat)
        self.assertEqual(p["seams"], "blend")
        self.assertIn("начальный кадр", p["note"])

    def test_the_honest_phrase_is_the_same_in_the_knowledge_file(self):
        text = read(KNOW).replace("\n", " ")
        self.assertTrue(film.BLEND in text, "в сайт-как-фильм.md нет фразы film.BLEND")


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + list(args), check=True, capture_output=True)


def probe(path, *args):
    r = subprocess.run(["ffprobe", "-v", "error"] + list(args) + [path], capture_output=True, text=True, check=True)
    return r.stdout


def pixel(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True)
    return tuple(r.stdout[:3])


def atoms(path):
    names, data = [], read(path, "rb")
    i = 0
    while i + 8 <= len(data):
        size = int.from_bytes(data[i:i + 4], "big")
        names.append(data[i + 4:i + 8].decode("latin-1"))
        if size == 1:
            size = int.from_bytes(data[i + 8:i + 16], "big")
        if size < 8:
            break
        i += size
    return names


def synthetic(path, hue, size="640x360", secs=2):
    ff("-f", "lavfi", "-i", "testsrc=size=%s:rate=24:duration=%s" % (size, secs), "-f", "lavfi", "-i",
       "sine=frequency=440:duration=%s" % secs, "-vf", "hue=h=%d:s=3" % hue, "-shortest", "-c:v", "libx264",
       "-g", "48", "-c:a", "aac", path)


@unittest.skipUnless(HAS_FF, "нет ffmpeg")
class FramesAndEncode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="film-ff-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_first_and_last_frame_are_the_real_ones(self):
        src = os.path.join(self.tmp, "rb.mp4")
        ff("-f", "lavfi", "-i", "color=c=red:s=160x90:d=1:r=24", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=1:r=24",
           "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-c:v", "libx264", "-pix_fmt", "yuv420p", src)
        r = cli("frames", src, "--first", os.path.join(self.tmp, "a.png"))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = cli("frames", src, "--last", os.path.join(self.tmp, "z.png"))
        self.assertEqual(r.returncode, 0, r.stderr)
        first, last = pixel(os.path.join(self.tmp, "a.png")), pixel(os.path.join(self.tmp, "z.png"))
        self.assertGreater(first[0], 200)
        self.assertLess(first[2], 60)
        self.assertGreater(last[2], 200)
        self.assertLess(last[0], 60)

    def keyframe_gap(self, path):
        flags = [int(x) for x in probe(path, "-select_streams", "v", "-show_entries", "frame=key_frame",
                                       "-of", "default=nw=1:nk=1").split()]
        keys = [i for i, k in enumerate(flags) if k]
        return max(b - a for a, b in zip(keys, keys[1:] + [len(flags)]))

    def has_audio(self, path):
        return "audio" in probe(path, "-show_entries", "stream=codec_type", "-of", "csv=p=0")

    def test_desktop_encode_is_scrubbable(self):
        src = os.path.join(self.tmp, "src.mp4")
        synthetic(src, 0)
        self.assertTrue(self.has_audio(src))
        out = os.path.join(self.tmp, "film", "b1.mp4")
        r = cli("encode", src, "--desktop", out, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLessEqual(self.keyframe_gap(out), 8)               # частые ключевые кадры
        self.assertFalse(self.has_audio(out))                         # без звука
        names = atoms(out)
        self.assertLess(names.index("moov"), names.index("mdat"))     # faststart

    def test_mobile_encode_is_a_9_16_canvas_and_says_when_cropped(self):
        src = os.path.join(self.tmp, "src.mp4")
        synthetic(src, 120)
        out = os.path.join(self.tmp, "b1-m.mp4")
        r = cli("encode", src, "--mobile", out, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        wh = probe(out, "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0").strip()
        self.assertEqual(wh, "720,1280")
        self.assertLessEqual(self.keyframe_gap(out), 4)
        self.assertFalse(self.has_audio(out))
        self.assertTrue(any("обрезка" in n for n in data["notes"]))   # горизонтальный исходник — честно
        r = cli("encode", src, "--mobile", out, "--fit", "pad", "--json")
        self.assertTrue(json.loads(r.stdout)["file"].endswith("b1-m-2.mp4"))   # не перезаписывает

    def toolset(self, cwebp):
        """Папка программ для AIDESIGN_MEDIA_PATH: ffmpeg без libwebp (подмена списка кодировщиков)
        и, по желанию, настоящий cwebp."""
        if os.name != "posix":
            self.skipTest("подмена ffmpeg — shell-скрипт")
        tools = tempfile.mkdtemp(prefix="tools-", dir=self.tmp)
        real = shutil.which("ffmpeg")
        fake = os.path.join(tools, "ffmpeg")
        with open(fake, "w", encoding="utf-8") as f:
            f.write('#!/bin/sh\nfor a in "$@"; do if [ "$a" = "-encoders" ]; then "%s" "$@" | grep -v libwebp; exit 0; fi; done\n'
                    'exec "%s" "$@"\n' % (real, real))
        os.chmod(fake, 0o755)
        if cwebp:
            if not shutil.which("cwebp"):
                self.skipTest("нет cwebp")
            os.symlink(shutil.which("cwebp"), os.path.join(tools, "cwebp"))
        return dict(os.environ, AIDESIGN_MEDIA_PATH=tools)

    def red_clip(self):
        src = os.path.join(self.tmp, "r.mp4")
        ff("-f", "lavfi", "-i", "color=c=red:s=160x90:d=1:r=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", src)
        return src

    def test_webp_frame_without_libwebp_goes_through_cwebp(self):
        env = self.toolset(cwebp=True)
        out = os.path.join(self.tmp, "film", "b1.webp")
        r = subprocess.run([sys.executable, FILM, "frames", self.red_clip(), "--first", out, "--json"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["file"], out)
        head = read(out, "rb")[:12]
        self.assertEqual((head[:4], head[8:12]), (b"RIFF", b"WEBP"))
        self.assertGreater(pixel(out)[0], 200)                                # тот же красный кадр

    def test_webp_frame_without_any_webp_encoder_is_a_png_with_a_note(self):
        env = self.toolset(cwebp=False)
        out = os.path.join(self.tmp, "b1.webp")
        r = subprocess.run([sys.executable, FILM, "frames", self.red_clip(), "--first", out],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        png = os.path.join(self.tmp, "b1.png")
        self.assertEqual(read(png, "rb")[:8], b"\x89PNG\r\n\x1a\n")
        self.assertFalse(os.path.exists(out))
        self.assertIn("PNG", r.stdout)
        self.assertIn("setup.py install webp", r.stdout)

    def test_no_ffmpeg_is_an_input_error_with_a_hint(self):
        env = dict(os.environ, AIDESIGN_MEDIA_PATH=self.tmp)
        r = subprocess.run([sys.executable, FILM, "frames", FILM, "--first", os.path.join(self.tmp, "x.png")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("setup.py plan ffmpeg", r.stderr)


def build_site(root, mobile=True, scenes=3, links=None, prose=False):
    """Синтетические сцены; по умолчанию три: связка между первой и второй, дальше — перетекание.
    Телефонные постеры — первые кадры телефонных роликов (frames --first), как в плане.
    prose — подписи сцен длиной с настоящие (для проверки страницы check.py)."""
    raw, site = os.path.join(root, "raw"), os.path.join(root, "site")
    os.makedirs(raw)
    links = ["c1", None] if links is None else links
    names = ["b%d" % i for i in range(1, scenes + 1)] + [x for x in links if x]
    for k, name in enumerate(names):
        src = os.path.join(raw, name + ".mp4")
        synthetic(src, (k * 67) % 360, size="320x180")
        film.encode(src, "desktop", os.path.join(site, "film", name + ".mp4"))
        if mobile:
            film.encode(src, "mobile", os.path.join(site, "film", name + "-m.mp4"))
        if name.startswith("b"):
            film.frames(os.path.join(site, "film", name + ".mp4"), "first", os.path.join(site, "film", name + ".jpg"))
            if mobile:
                film.frames(os.path.join(site, "film", name + "-m.mp4"), "first",
                            os.path.join(site, "film", name + "-m.jpg"))
    beats = [{"id": b, "title": "Сцена %d" % i, "body": "Фраза %d." % i, "still": "film/%s.jpg" % b,
              "stillMobile": "film/%s-m.jpg" % b if mobile else None,
              "clip": "film/%s.mp4" % b, "clipMobile": "film/%s-m.mp4" % b if mobile else None, "scroll": 1.6}
             for i, b in enumerate(names[:scenes], 1)]
    if prose:
        for i, b in enumerate(beats, 1):
            b["title"] = "Как мы варим кофе: сцена %d" % i
            b["body"] = ("Зерно приезжает из маленькой обжарки в соседнем квартале, и каждое утро мы пробуем "
                         "его заново, прежде чем открыть двери гостям.")
    plan ={"version": 1, "title": "Синтетический фильм", "beats": beats,
            "connectors": ["film/%s.mp4" % x if x else None for x in links],
            "connectorsMobile": ["film/%s-m.mp4" % x if x else None for x in links] if mobile else [],
            "cta": {"label": "Записаться", "href": "#"}, "after": "Дальше — обычные разделы."}
    path = os.path.join(root, "film-plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    return path, site


@unittest.skipUnless(HAS_FF, "нет ffmpeg")
class Page(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="film-page-")
        self.plan, self.site = build_site(self.tmp, mobile=False)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_page_is_built_on_the_engine_and_is_an_ordinary_page_underneath(self):
        r = cli("page", "--plan", self.plan, "--out", self.site, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = read(os.path.join(self.site, "index.html"))
        self.assertTrue(os.path.isfile(os.path.join(self.site, "scroll-film.js")))
        self.assertIn('<script src="scroll-film.js"></script>', text)
        self.assertIn("data-film", text)
        self.assertEqual(text.count('<article class="sf-beat"'), 3)    # кадры и текст в обычном потоке
        self.assertEqual(text.count("<h1>"), 1)
        self.assertIn('"connectors": ["film/c1.mp4", null]', text)
        check = load("aidesign_check", os.path.join(TOOLS, "check.py"))
        self.assertEqual([(f.rule, f.line) for f in check.scan([os.path.join(self.site, "index.html")])], [])

    def test_missing_files_are_listed_and_index_is_not_overwritten(self):
        os.remove(os.path.join(self.site, "film", "b2.mp4"))
        r = cli("page", "--plan", self.plan, "--out", self.site, "--json")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stdout)["missing"], ["film/b2.mp4"])
        self.assertEqual(cli("page", "--plan", self.plan, "--out", self.site).returncode, 1)

    def test_force_rewrites_only_its_own_film_page_and_engine(self):
        self.assertEqual(cli("page", "--plan", self.plan, "--out", self.site).returncode, 0)
        self.assertEqual(cli("page", "--plan", self.plan, "--out", self.site, "--force").returncode, 0)
        index, engine = os.path.join(self.site, "index.html"), os.path.join(self.site, "scroll-film.js")
        with open(index, "w", encoding="utf-8") as f:
            f.write("<!doctype html><title>Главная человека</title>")
        r = cli("page", "--plan", self.plan, "--out", self.site, "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Главная человека", read(index))                # чужая главная не тронута
        os.remove(index)
        with open(engine, "w", encoding="utf-8") as f:
            f.write("// чужой скрипт")
        self.assertEqual(cli("page", "--plan", self.plan, "--out", self.site, "--force").returncode, 1)
        self.assertEqual(read(engine), "// чужой скрипт")
        self.assertFalse(os.path.exists(index))

    def test_engine_keeps_video_src_as_the_main_path(self):
        js = read(os.path.join(SKILL, "assets", "scroll-film.js"))
        self.assertIn("s.video.src = s.url", js)                       # прямой src
        self.assertIn("URL.revokeObjectURL", js)
        self.assertRegex(js, r"http\s*&&\s*cfg\.blob")                 # Blob — только по http
        self.assertIn("prefers-reduced-motion", js)


class SeamsVerdict(unittest.TestCase):
    """Вердикт seams по ответу браузера: браузер подменён, ответ — как у film-seams.mjs."""

    def answer(self, times_by_span):
        seam = {"i": 1, "y": 900, "band": 40, "from": "beat", "to": "beat",
                "before": {"settled": True, "segment": 0, "file": "b.png"},
                "after": {"settled": True, "segment": 1, "file": "a.png"}}
        track = [{"y": 100 * k + j, "p": p, "settled": True, "segment": k, "span": k, "time": t, "duration": 4.0}
                 for k, times in enumerate(times_by_span) for j, (p, t) in enumerate(zip((0.3, 0.5, 0.7), times))]
        return {"ok": True, "browser": "fake", "seams": [seam], "track": track, "stats": {}, "errors": []}

    def run_with(self, res):
        class Fake:
            SCRIPTS = TOOLS
            BrowserError = RuntimeError

            @staticmethod
            def run(script, args, timeout):
                return res
        tmp = tempfile.mkdtemp(prefix="film-verdict-")
        self.addCleanup(shutil.rmtree, tmp)
        real = film._browser
        film._browser = lambda: Fake
        try:
            return film.seams("http://127.0.0.1:1/index.html", os.path.join(tmp, "shots"))
        finally:
            film._browser = real

    def test_time_growing_with_scroll_is_ok(self):
        r = self.run_with(self.answer([[0.5, 1.2, 2.0], [0.4, 1.1, 1.9]]))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["frozen"], [])

    def test_a_freeze_frame_segment_is_not_ok(self):
        r = self.run_with(self.answer([[0.5, 1.2, 2.0], [0.0, 0.0, 0.0]]))
        self.assertFalse(r["ok"])
        self.assertEqual(r["frozen"], [1])


def browser_ready():
    try:
        return load("aidesign_browser_probe", os.path.join(TOOLS, "browser.py")).ready()
    except Exception:  # noqa: BLE001 — нет модуля: живой класс пропускается
        return False


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@unittest.skipUnless(HAS_FF and browser_ready(), "нет ffmpeg или браузерный модуль не поставлен (browser.py ensure --yes)")
class LiveFilm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="film-live-")
        plan, cls.site = build_site(cls.tmp)
        film.page(plan, cls.site)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def range_server(self):
        port = free_port()
        proc = subprocess.Popen([sys.executable, AD, "--serve-http", str(port), "--directory", self.site],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.wait(proc, port)

    def plain_server(self):
        port = free_port()
        proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                                 "--directory", self.site], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.wait(proc, port)

    def wait(self, proc, port):
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        url = "http://127.0.0.1:%d/index.html" % port
        for _ in range(50):
            try:
                urllib.request.urlopen(url, timeout=1).close()
                return url
            except OSError:
                time.sleep(0.1)
        self.fail("сервер не поднялся")

    def run_seams(self, page, **kw):
        out = tempfile.mkdtemp(prefix="shots-", dir=self.tmp)
        return film.seams(page, out, **kw), out

    def assert_film(self, r, proto, suffix=".mp4"):
        self.assertTrue(r["ok"], (r.get("errors"), r.get("unsettled"), r.get("stuck")))
        self.assertEqual([(s["from"], s["to"]) for s in r["seams"]], [("beat", "link"), ("link", "beat"), ("beat", "beat")])
        for s in r["seams"]:
            b, a = s["before"], s["after"]
            self.assertEqual(a["segment"], b["segment"] + 1)              # стык переходит к следующему клипу
            self.assertGreater(b["time"], 0.75 * b["duration"])           # до стыка — конец клипа
            self.assertLess(a["time"], 0.25 * a["duration"])              # после — его начало
            self.assertTrue(os.path.getsize(b["file"]) and os.path.getsize(a["file"]))
        for seg in range(4):                                              # время идёт за прокруткой
            times = [t["time"] for t in r["track"] if t["segment"] == seg]
            self.assertEqual(len(times), 3, r["track"])
            self.assertTrue(times[0] < times[1] < times[2], times)
        self.assertTrue(all(t["proto"] == proto and (t["clip"] == "blob" or t["clip"].endswith(suffix)) for t in r["track"]),
                        r["track"])

    def test_scrubs_over_http_with_range_by_direct_src(self):
        r, _ = self.run_seams(self.range_server())
        self.assert_film(r, "http")
        self.assertEqual(r["stats"]["blobs"], 0)                          # сервер с Range — Blob не нужен

    def test_scrubs_when_opened_as_a_file(self):
        r, _ = self.run_seams(os.path.join(self.site, "index.html"))
        self.assert_film(r, "file")
        self.assertEqual(r["stats"]["blobs"], 0)

    def test_server_without_range_gets_a_blob_and_it_is_released(self):
        r, _ = self.run_seams(self.plain_server())
        self.assertTrue(r["ok"], r.get("errors"))
        self.assertGreater(r["stats"]["blobs"], 0)
        self.assertGreater(r["stats"]["revoked"], 0)                      # дальние клипы выгружены, память отдана

    def test_phone_390_gets_the_mobile_files(self):
        r, _ = self.run_seams(self.range_server(), mobile=True)
        self.assert_film(r, "http", suffix="-m.mp4")

    def test_reduced_motion_is_an_ordinary_page(self):
        r, out = self.run_seams(os.path.join(self.site, "index.html"), reduced=True)
        self.assertFalse(r["still"]["mounted"])
        self.assertEqual(r["still"]["videos"], 0)
        self.assertEqual(r["still"]["images"], 3)
        self.assertTrue(os.path.isfile(os.path.join(out, "reduced-motion.png")))

    def test_seams_do_not_overwrite_earlier_shots(self):
        out = tempfile.mkdtemp(prefix="shots-twice-", dir=self.tmp)
        page = os.path.join(self.site, "index.html")
        first = film.seams(page, out, reduced=True)
        stamp = os.path.getmtime(first["shot"])
        second = film.seams(page, out, reduced=True)
        self.assertEqual(second["out"], out + "-2")
        self.assertEqual(os.path.getmtime(first["shot"]), stamp)

    def test_first_screen_loads_only_the_first_poster(self):
        r, _ = self.run_seams(os.path.join(self.site, "index.html"))
        self.assertEqual(r["start"]["posters"], 1)


@unittest.skipUnless(HAS_FF and browser_ready(), "нет ffmpeg или браузерный модуль не поставлен (browser.py ensure --yes)")
class LiveFilmPassesCheck(unittest.TestCase):
    """Страница фильма проходит собственную проверку: check.py и check.py --browser без находок.
    Подписи сцен появляются по прокрутке намеренно, но остаются в потоке чтения (не inert)."""

    def test_film_page_has_no_findings_static_and_in_browser(self):
        tmp = tempfile.mkdtemp(prefix="film-check-")
        self.addCleanup(shutil.rmtree, tmp)
        plan, site = build_site(tmp, prose=True)
        film.page(plan, site)
        check = os.path.join(TOOLS, "check.py")
        for args in ([site], ["--browser", os.path.join(site, "index.html")]):
            r = subprocess.run([sys.executable, "-B", check] + args + ["--json"], capture_output=True, text=True,
                               encoding="utf-8", timeout=600)
            with self.subTest(args=args[0]):
                self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])
                self.assertEqual(json.loads(r.stdout)["findings"], [])


@unittest.skipUnless(HAS_FF and browser_ready(), "нет ffmpeg или браузерный модуль не поставлен (browser.py ensure --yes)")
class LiveLongFilmOnPhone(unittest.TestCase):
    """Фильм из 7 отрезков на телефоне 390: в памяти не больше трёх роликов, дальние выгружаются."""

    def test_far_clips_are_unloaded(self):
        tmp = tempfile.mkdtemp(prefix="film-long-")
        self.addCleanup(shutil.rmtree, tmp)
        plan, site = build_site(tmp, scenes=4, links=["c1", "c2", "c3"])
        film.page(plan, site)
        r = film.seams(os.path.join(site, "index.html"), os.path.join(tmp, "shots"), mobile=True)
        self.assertTrue(r["ok"], (r.get("errors"), r.get("unsettled"), r.get("stuck")))
        self.assertEqual(r["start"]["segments"], 7)
        self.assertLessEqual(max(t["loaded"] for t in r["track"]), 3, [t["loaded"] for t in r["track"]])
        self.assertGreater(r["stats"]["unloaded"], 0)
        self.assertTrue(all(t["clip"].endswith("-m.mp4") for t in r["track"]))


if __name__ == "__main__":
    unittest.main()
