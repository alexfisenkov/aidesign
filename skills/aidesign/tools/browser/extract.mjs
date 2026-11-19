// Стиль страницы для extract.py: открывает адрес как обычный посетитель (без маскировки),
// закрывает окно cookies кнопкой «принять», читает отрисованные стили и состояния кнопок.
// Аргумент — JSON {url, dark, mobile, timeoutMs}; ответ — одна строка JSON (см. extract_style.py).
import { main, loadPlaywright, launch, honestAgent } from './common.mjs';
import { dismissConsent } from './consent.mjs';
import { installHelpers, collectPage, signature } from './collect.mjs';
import { guardContext, urlProblem } from './guard.mjs';

const LIMIT = 2500;
const CHALLENGE = /just a moment|attention required|checking your browser|access denied|captcha|подтвердите, что вы не робот/i;
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

function context(browser, ua, { mobile, dark }) {
  const opts = { userAgent: ua, colorScheme: dark ? 'dark' : 'light', locale: 'ru-RU',
    viewport: mobile ? { width: 390, height: 844 } : { width: 1280, height: 800 } };
  if (mobile) Object.assign(opts, { isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  return browser.newContext(opts);
}

async function open(browser, ua, a) {
  const ctx = await context(browser, ua, a);
  const page = await ctx.newPage();
  const css = [];
  page.on('response', async (resp) => {
    try {
      if (resp.request().resourceType() !== 'stylesheet' || css.length >= 40) return;
      const text = (await resp.text()).slice(0, 3e6);
      for (const m of text.matchAll(/@media([^{]+)\{/g)) css.push(m[1].trim());
    } catch {}
  });
  const stop = {};
  const guardOpts = { allowLocal: !!a.allowLocal, ownSite: !!a.ownSite };
  await guardContext(ctx, page, guardOpts, stop);
  const halt = () => { if (stop.reason) throw new Error(stop.reason); };
  let resp;
  try {
    resp = await page.goto(a.url, { waitUntil: 'domcontentloaded', timeout: a.timeoutMs });
  } catch (e) {
    halt();
    throw e;
  }
  halt();
  for (let r = resp && resp.request(); r; r = r.redirectedFrom()) {   // каждый шаг редиректа — ещё раз
    const why = await urlProblem(r.url(), { ...guardOpts, robots: true });
    if (why) throw new Error(why);
  }
  const status = resp ? resp.status() : 0;
  if (status >= 400) throw new Error(`страница ответила ${status} — сайт не пускает или адреса нет`);
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await pause(800);
  const title = await page.title().catch(() => '');
  if (CHALLENGE.test(title)) throw new Error('сайт показывает проверку «вы не робот» — обходить не будем, нужны скриншоты');
  const consent = await dismissConsent(page);
  if (consent) await pause(800);
  for (let i = 1; i <= 4; i++) {                            // ленивые блоки и появления при прокрутке
    await page.evaluate((k) => window.scrollTo(0, document.body ? document.body.scrollHeight * k / 4 : 0), i).catch(() => {});
    await pause(250);
  }
  await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
  await pause(400);
  halt();                                                   // страница сама ушла на запрещённый адрес
  return { ctx, page, css, status, consent, halt };
}

async function states(page, selector, kinds, limit) {
  const out = [];
  const seen = new Set();
  const handles = (await page.$$(selector)).slice(0, 60);
  for (const h of handles) {
    if (out.length >= limit) break;
    const sig = await h.evaluate(signature).catch(() => null);
    if (!sig || seen.has(sig)) continue;
    seen.add(sig);
    const item = { base: await h.evaluate((el) => window.__aidesign.snap(el)) };
    for (const kind of kinds) {
      try {
        if (kind === 'hover') await h.hover({ timeout: 1500 });
        else await h.focus();
        await pause(450);                                 // переход цвета успевает доиграть
        item[kind] = await h.evaluate((el) => window.__aidesign.snap(el));
      } catch {}
      await page.mouse.move(0, 0).catch(() => {});
      await h.evaluate((el) => el.blur && el.blur()).catch(() => {});
      await pause(200);
    }
    out.push(item);
  }
  return out;
}

async function read(page, css, withStates) {
  await page.evaluate(installHelpers);
  const data = await page.evaluate(collectPage, LIMIT);
  data.media = Array.from(new Set(data.media.concat(css)));
  if (withStates) {
    data.buttons = await states(page, 'button, [role="button"], input[type="submit"], input[type="button"], ' +
      'a[class*="btn" i], a[class*="button" i]', ['hover', 'focus'], 8);
    data.inputs = await states(page, 'input:not([type]), input[type="text"], input[type="email"], input[type="search"], ' +
      'input[type="tel"], textarea, select', ['focus'], 4);
    data.links = await states(page, 'a[href]:not([class*="btn" i]):not([class*="button" i]):not([role="button"])',
      ['hover'], 4);
  }
  return data;
}

main(async (a) => {
  if (!/^https?:\/\//i.test(a.url || '')) throw new Error('нужен адрес http(s)');
  a.timeoutMs = a.timeoutMs || 60000;
  const { browser, name } = await launch(loadPlaywright());
  try {
    const ua = await honestAgent(browser);
    const light = await open(browser, ua, { ...a, dark: false });
    const raw = await read(light.page, light.css, true);
    light.halt();
    Object.assign(raw, { ok: true, url: a.url, finalUrl: light.page.url(), status: light.status, browser: name,
      browserVersion: browser.version(), viewport: light.page.viewportSize(), consent: light.consent });
    await light.ctx.close();
    if (a.dark) {
      const dark = await open(browser, ua, { ...a, dark: true });
      raw.dark = await read(dark.page, dark.css, false);
      dark.halt();
      await dark.ctx.close();
    }
    return raw;
  } finally {
    await browser.close();
  }
});
