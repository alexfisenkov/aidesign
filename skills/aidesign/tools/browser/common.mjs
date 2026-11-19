// Общее для скриптов браузерного модуля AI Design: пакет из общего кэша, запуск браузера,
// честный User-Agent, ответ одной строкой JSON. Запускает browser.py (run).
import { createRequire } from 'node:module';
import path from 'node:path';

export const AGENT = 'AIDesign/0.4 (+style reference; respects robots.txt)';

export function firstLine(e) {
  const text = String((e && e.message) || e || 'ошибка');
  return text.split('\n').map((s) => s.trim()).find((s) => s && !/^[═║╔╗╚╝─]+$/.test(s)) || text;
}

export function loadPlaywright() {
  const home = process.env.AIDESIGN_NODE_HOME;
  if (!home) throw new Error('AIDESIGN_NODE_HOME не задан — запускайте через browser.py');
  return createRequire(path.join(home, 'package.json'))('playwright');
}

// Chromium Playwright, затем Chrome и Edge компьютера. AIDESIGN_BROWSER_CHANNEL — только один.
export async function launch(pw) {
  const forced = process.env.AIDESIGN_BROWSER_CHANNEL;
  const order = forced ? [forced] : ['chromium', 'chrome', 'msedge'];
  const tried = [];
  for (const name of order) {
    try {
      const opts = name === 'chromium' ? { headless: true } : { headless: true, channel: name };
      const browser = await pw.chromium.launch(opts);
      return { browser, name, tried };
    } catch (e) {
      tried.push({ browser: name, error: firstLine(e) });
    }
  }
  const err = new Error('браузер не запустился: ' + tried.map((t) => `${t.browser} — ${t.error}`).join('; '));
  err.tried = tried;
  throw err;
}

// User-Agent браузера как есть (с HeadlessChrome) и пометка, кто пришёл.
export async function honestAgent(browser) {
  const ctx = await browser.newContext();
  try {
    const page = await ctx.newPage();
    const ua = await page.evaluate(() => navigator.userAgent);
    return `${ua} ${AGENT}`;
  } finally {
    await ctx.close();
  }
}

export function args() {
  try { return JSON.parse(process.argv[2] || '{}'); } catch { return {}; }
}

export async function main(work) {
  let out;
  try {
    out = await work(args());
  } catch (e) {
    out = { ok: false, error: firstLine(e), tried: e.tried || [] };
  }
  process.stdout.write(JSON.stringify(out) + '\n', () => process.exit(out.ok === false ? 1 : 0));
}
