// AI Design, «сайт как фильм»: снимки до и после каждого стыка и проверка, что время видео идёт
// за прокруткой. Запускает film.py seams через browser.py run; общий код браузерного модуля
// (пакет из кэша, ответ JSON) берётся из args.common — путь к browser/common.mjs.
// Браузер: Chrome, затем Edge компьютера (в них есть H.264), затем Chromium Playwright.
// По мотивам: oso95/scroll-world references/pipeline.md, проверка стыков (MIT, © 2026 cyw) и
// MengTo/Skills scroll-world-storytelling (MIT, © 2026 Meng To). Изменено: написано заново.
import { pathToFileURL } from 'node:url';

const given = JSON.parse(process.argv[2] || '{}');
const common = await import(pathToFileURL(given.common).href);

async function open(pw) {
  const forced = process.env.AIDESIGN_BROWSER_CHANNEL;
  const order = forced ? [forced] : ['chrome', 'msedge', 'chromium'];
  const tried = [];
  for (const name of order) {
    try {
      const opts = name === 'chromium' ? { headless: true } : { headless: true, channel: name };
      return { browser: await pw.chromium.launch(opts), name };
    } catch (e) { tried.push(`${name} — ${common.firstLine(e)}`); }
  }
  throw new Error('браузер не запустился: ' + tried.join('; '));
}

const TOP = () => {
  const f = window.ScrollFilm && window.ScrollFilm.instances[0];
  if (!f) return null;
  const all = f.state();
  const st = all.filter((s) => s.op > 0.5);
  const s = st[st.length - 1];
  return s ? { segments: all.length, loaded: all.filter((x) => x.loaded).length,
               posters: document.querySelectorAll('.sf-scene img[src]').length, segment: s.k, kind: s.kind, beat: s.beat, time: +s.time.toFixed(3), duration: +s.duration.toFixed(3),
               ready: s.ready, blob: s.blob, seekableEnd: +s.seekableEnd.toFixed(3),
               proto: s.src.split(':')[0], clip: s.blob ? 'blob' : s.src.split('/').pop() } : null;
};

common.main(async (a) => {
  const pw = common.loadPlaywright();
  const { browser, name } = await open(pw);
  const errors = [];
  try {
    const ctx = await browser.newContext(a.mobile
      ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: a.reducedMotion ? 'reduce' : 'no-preference' }
      : { viewport: { width: 1280, height: 800 }, reducedMotion: a.reducedMotion ? 'reduce' : 'no-preference' });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(common.firstLine(e)));
    page.on('console', (m) => {
      if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) errors.push(m.text().slice(0, 200));
    });
    page.on('response', (r) => {                         // файл не найден — с адресом; значок сайта не в счёт
      if (r.status() >= 400 && !/\/favicon\.ico$/.test(r.url())) errors.push(`${r.status()} ${r.url().split('/').pop()}`);
    });
    page.on('requestfailed', (r) => {
      if (!/\/favicon\.ico$/.test(r.url()) && !/ERR_ABORTED/.test((r.failure() || {}).errorText || '')) {
        errors.push(`не загрузилось: ${r.url().split('/').pop()}`);
      }
    });
    await page.goto(a.url, { waitUntil: 'load', timeout: 30000 });
    const shot = async (file) => { await page.screenshot({ path: file }); return file; };
    if (a.reducedMotion) {
      const still = await page.evaluate(() => ({
        mounted: !!(window.ScrollFilm && window.ScrollFilm.instances.length),
        videos: document.querySelectorAll('video[src]').length,
        images: document.querySelectorAll('.sf-beat img').length,
        height: document.documentElement.scrollHeight,
      }));
      return { ok: true, browser: name, mode: 'reduced-motion', still, shot: await shot(a.out + '/reduced-motion.png'), errors };
    }
    await page.waitForFunction(() => window.ScrollFilm && window.ScrollFilm.instances.length, null, { timeout: 10000 });
    const settle = async (y) => {
      // Событие scroll приходит к следующему кадру — ждём два кадра, иначе цели движка ещё прежние.
      await page.evaluate((v) => new Promise((done) => {
        window.scrollTo(0, v);
        requestAnimationFrame(() => requestAnimationFrame(done));
      }), y);
      try {
        await page.waitForFunction(() => window.ScrollFilm.instances[0].settled(), null, { timeout: a.settleMs || 6000, polling: 50 });
        return true;
      } catch { return false; }
    };
    const seams = await page.evaluate(() => window.ScrollFilm.instances[0].seams());
    const start = { settled: await settle(0), ...(await page.evaluate(TOP)), file: await shot(`${a.out}/start.png`) };
    const out = [];
    for (const s of seams) {
      const pad = Math.ceil(s.band / 2) + 4;
      const n = String(s.i).padStart(2, '0');
      const okB = await settle(s.y - pad);
      const before = { y: s.y - pad, settled: okB, ...(await page.evaluate(TOP)), file: await shot(`${a.out}/seam-${n}-before.png`) };
      const okA = await settle(s.y + pad);
      const after = { y: s.y + pad, settled: okA, ...(await page.evaluate(TOP)), file: await shot(`${a.out}/seam-${n}-after.png`) };
      out.push({ i: s.i, y: s.y, band: s.band, from: s.from, to: s.to, before, after });
    }
    // Время видео за прокруткой: по три точки на каждый отрезок цепочки (span — номер отрезка с 0).
    // Вердикт считает film.py seams: время внутри отрезка обязано расти, иначе стоп-кадр и ok=false.
    const spans = await page.evaluate(() => {
      const f = window.ScrollFilm.instances[0];
      const top = f.root.getBoundingClientRect().top + window.scrollY;
      const vh = innerHeight;
      const ss = f.seams();
      const edges = [top].concat(ss.map((s) => s.y)).concat([top + f.root.offsetHeight - vh]);
      return edges.slice(0, -1).map((e, k) => [e, edges[k + 1]]);
    });
    const track = [];
    for (const [span, [s0, s1]] of spans.entries()) {
      for (const p of [0.3, 0.5, 0.7]) {
        const y = Math.round(s0 + (s1 - s0) * p);
        const settled = await settle(y);
        track.push({ y, p, span, settled, ...(await page.evaluate(TOP)) });
      }
    }
    const stats = await page.evaluate(() => window.ScrollFilm.instances[0].stats);
    return { ok: true, browser: name, url: a.url, mobile: !!a.mobile, start, seams: out, track, stats, errors };
  } finally {
    await browser.close();
  }
});
