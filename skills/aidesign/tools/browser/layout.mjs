// По мотивам: pbakaus/impeccable (Apache-2.0) — crates/core/src/browser/{page_checks,line_breaks,quality}.rs;
// код написан заново, пороги — из источника. Изменено: свой набор проверок, один проход на экран.
// Правила раскладки для check.py --browser: страница открывается на 1280×800 и 390×844,
// прокручивается до конца (чтобы сработали появления) и меряется по отрисовке.
// Вход (JSON): {targets: [адрес…], viewports: [[w,h]…], waitMs}. Выход: {ok, results:[{target,
// viewport, findings:[{rule, tag, id, cls, text, detail}], error}]}. Тексты страниц не сохраняются,
// кроме первых слов найденного элемента — чтобы человек нашёл место.
import { main, loadPlaywright, launch, honestAgent, firstLine } from './common.mjs';

main(async (args) => {
  const pw = loadPlaywright();
  const { browser, name } = await launch(pw);
  const ua = await honestAgent(browser);
  const viewports = args.viewports || [[1280, 800], [390, 844]];
  const results = [];
  try {
    for (const target of args.targets || []) {
      for (const [w, h] of viewports) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, userAgent: ua });
        const page = await ctx.newPage();
        const errors = [];
        page.on('pageerror', (e) => errors.push(firstLine(e)));
        const item = { target, viewport: [w, h], findings: [] };
        try {
          await page.goto(target, { waitUntil: 'load', timeout: (args.timeoutS || 30) * 1000 });
          await page.evaluate(scrollThrough);
          await page.waitForTimeout(args.waitMs ?? 700);
          item.findings = await page.evaluate(collect, { w, h });
          for (const msg of [...new Set(errors)]) item.findings.push({ rule: 'script-error', tag: '', id: '', cls: '', text: '', detail: msg.slice(0, 160) });
        } catch (e) {
          item.error = firstLine(e);
        }
        await ctx.close();
        results.push(item);
      }
    }
  } finally {
    await browser.close();
  }
  return { ok: true, browser: name, results };
});

// Прокрутка до конца и обратно: так срабатывают появления по прокрутке и ленивая загрузка.
// По пути запоминается текст, который хоть раз был виден на экране (window.__aidesignSeen):
// сцена фильма по прокрутке показывает свой текст на своём месте и прячет дальше — это не
// «скрыто в покое», если текст при этом остаётся в потоке чтения (не inert).
async function scrollThrough() {
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  const seen = (window.__aidesignSeen = new WeakSet());
  const own = (el) => Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
  const pending = Array.from(document.body.querySelectorAll('*')).filter(own);
  const visible = (el) => {
    let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.display === 'none' || s.visibility === 'hidden') return false;
      o *= parseFloat(s.opacity) || 0;
    }
    const r = el.getBoundingClientRect();
    return o >= 0.5 && r.width > 1 && r.height > 1 && r.bottom > 0 && r.top < innerHeight;
  };
  const look = () => { for (const el of pending) if (!seen.has(el) && visible(el)) seen.add(el); };
  // Шаг полэкрана: окно, в котором сцена фильма показывает текст, не короче ~0.6 экрана.
  const step = Math.max(200, innerHeight * 0.5);
  for (let y = 0; y < document.documentElement.scrollHeight && y < 40000; y += step) {
    scrollTo(0, y);
    await pause(60);
    look();
  }
  scrollTo(0, 0);
  await pause(120);
}

// Всё, что ниже, выполняется внутри страницы и самодостаточно.
function collect({ w, h }) {
  const out = [];
  const cs = (el) => getComputedStyle(el);
  const info = (el) => ({
    tag: el.tagName.toLowerCase(), id: el.id || '',
    cls: ((el.getAttribute('class') || '').trim().split(/\s+/)[0]) || '',
    text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
  });
  const add = (rule, el, detail) => out.push({ rule, ...info(el), detail });
  const shown = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const s = cs(n);
      if (s.display === 'none' || s.visibility === 'hidden' || n.hidden || n.getAttribute('aria-hidden') === 'true') return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const inFixed = (el) => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) { const p = cs(n).position; if (p === 'fixed' || p === 'sticky') return true; } return false; };
  const inScroller = (el) => { for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) { const o = cs(n).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  const ownText = (el) => Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').replace(/\s+/g, ' ').trim();
  const opacity = (el) => { let o = 1; for (let n = el; n && n.nodeType === 1; n = n.parentElement) o *= parseFloat(cs(n).opacity) || 0; return o; };
  const lines = (el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const rows = [];
    for (const r of range.getClientRects()) {
      if (r.width < 1 || r.height < 1) continue;
      const row = rows.find((x) => Math.abs(x.top - r.top) < r.height * 0.5);
      if (row) { row.left = Math.min(row.left, r.left); row.right = Math.max(row.right, r.right); }
      else rows.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height });
    }
    return rows.sort((a, b) => a.top - b.top);
  };
  const texts = Array.from(document.body.querySelectorAll('*')).filter((el) =>
    !['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION', 'svg'].includes(el.tagName) && ownText(el).length > 1 && shown(el));
  const prose = (el) => /^(P|LI|DD|BLOCKQUOTE|FIGCAPTION)$/.test(el.tagName) && !el.closest('nav,[role=navigation],table');
  const limit = (rule, n) => out.filter((f) => f.rule === rule).length < n;

  // Вылет за край и обрезанный текст
  const docW = document.documentElement.clientWidth || w;
  for (const el of texts) {
    if (inFixed(el) || inScroller(el) || !limit('text-overflow', 5)) continue;
    const rows = lines(el);
    const right = Math.max(0, ...rows.map((r) => r.right));
    const left = Math.min(w, ...rows.map((r) => r.left));
    if (rows.length && (right > docW + 1 || left < -1)) { add('text-overflow', el, `текст уходит за край экрана на ${Math.round(Math.max(right - docW, -left))}px`); continue; }
    const s = cs(el);
    if ((s.overflowX === 'hidden' || s.overflowX === 'clip') && el.scrollWidth > el.clientWidth + 2 && s.textOverflow !== 'ellipsis')
      add('text-overflow', el, `текст обрезан рамкой на ${el.scrollWidth - el.clientWidth}px`);
  }
  // Абзац прижат к краю экрана
  const edge = w <= 480 ? 12 : 16;
  for (const el of texts) {
    if (!prose(el) || inFixed(el) || inScroller(el) || !limit('body-text-viewport-edge', 5)) continue;
    const rows = lines(el);
    if (!rows.length) continue;
    const gap = Math.min(...rows.map((r) => Math.min(r.left, docW - r.right)));
    if (gap >= 0 && gap < edge) add('body-text-viewport-edge', el, `до края экрана ${Math.round(gap)}px при норме ${edge}px`);
  }
  // Длина строки, висячая строка, несбалансированный заголовок
  for (const el of texts) {
    const rows = lines(el);
    if (rows.length < 2) continue;
    const txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
    const widths = rows.map((r) => r.right - r.left);
    const perPx = txt.length / widths.reduce((a, b) => a + b, 0);
    const maxW = Math.max(...widths);
    const words = txt.split(' ').length;
    if (prose(el) && widths.filter((x) => x * perPx > 80).length >= 2 && limit('line-length', 5))
      add('line-length', el, `до ${Math.round(maxW * perPx)} знаков в строке`);
    const last = widths[widths.length - 1];
    const wrap = `${cs(el).textWrap || ''} ${cs(el).textWrapStyle || ''}`;
    if (/pretty|balance/.test(wrap) || el.querySelector('br') || /pre/.test(cs(el).whiteSpace)) continue;   // перенос задан автором
    if (prose(el) && words >= 3 && maxW * perPx >= 30 && last / maxW < 0.3 && limit('straggler', 5)) {
      const tail = txt.split(' ').pop();
      if (tail && last * perPx <= tail.length + 2) add('straggler', el, `в последней строке одно слово «${tail.slice(0, 20)}»`);
    }
    if (/^H[1-6]$/.test(el.tagName) && rows.length <= 3 && words >= 3 && maxW * perPx >= 20
        && last / widths[widths.length - 2] < 0.35 && limit('unbalanced-heading', 5))
      add('unbalanced-heading', el, `последняя строка ${Math.round(100 * last / widths[widths.length - 2])}% от предыдущей`);
  }
  // Ритм заголовков: над заголовком места не меньше, чем под ним
  const heads = Array.from(document.querySelectorAll('h2,h3,h4')).filter(shown);
  let total = 0; const crowded = [];
  for (const hd of heads) {
    const prev = hd.previousElementSibling, next = hd.nextElementSibling;
    if (!prev || !next || !shown(prev) || !shown(next)) continue;
    const r = hd.getBoundingClientRect(), p = prev.getBoundingClientRect(), n = next.getBoundingClientRect();
    const above = r.top - p.bottom, below = n.top - r.bottom;
    if (above < -1 || below < 0) continue;
    total += 1;
    if (above <= below + 0.5) crowded.push(hd);
  }
  if (crowded.length >= 2 && crowded.length * 2 >= total) add('heading-rhythm', crowded[0], `${crowded.length} из ${total} заголовков ближе к блоку выше, чем к своему`);
  // Контент скрыт в покое. Не в счёт — текст, который при прокрутке был виден на своём месте и
  // остался в потоке чтения (не inert): так работает сцена «сайта как фильма» (антипаттерны.md#section-fade).
  const seen = window.__aidesignSeen || new WeakSet();
  let all = 0, hiddenChars = 0; let firstHidden = null;
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION'].includes(el.tagName) || el.closest('[hidden],[aria-hidden=true],details:not([open]),dialog:not([open])')) continue;
    const t = ownText(el);
    if (t.length < 2) continue;
    const s = cs(el);
    if (s.display === 'none') continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 && r.height <= 1) continue;
    all += t.length;
    if ((s.visibility === 'hidden' || opacity(el) < 0.05) && !(seen.has(el) && !el.closest('[inert]'))) { hiddenChars += t.length; firstHidden = firstHidden || el; }
  }
  if (all >= 200 && hiddenChars >= 150 && hiddenChars / all > 0.3) add('content-hidden-at-rest', firstHidden, `скрыто ${hiddenChars} из ${all} знаков после прокрутки`);
  // Перекрытие текста: верхний слой в точках строк — не сам элемент и не его родня
  const docH = document.documentElement.scrollHeight;
  for (let y0 = 0; y0 < docH && y0 < 20000; y0 += h) {
    scrollTo(0, y0);
    for (const el of texts) {
      if (!limit('text-occlusion', 5) || opacity(el) < 0.5) continue;
      for (const row of lines(el).slice(0, 3)) {
        if (row.top < 0 || row.bottom > h) continue;
        const y = (row.top + row.bottom) / 2;
        const hits = [0.25, 0.5, 0.75].map((k) => document.elementsFromPoint(row.left + (row.right - row.left) * k, y)[0]).filter(Boolean);
        const cover = hits.find((top) => top !== el && !el.contains(top) && !top.contains(el) && !inFixed(top) && opaque(top));
        if (cover) { add('text-occlusion', el, `закрыт элементом <${cover.tagName.toLowerCase()}${cover.className && typeof cover.className === 'string' ? '.' + cover.className.split(' ')[0] : ''}>`); break; }
      }
    }
  }
  scrollTo(0, 0);
  function opaque(el) {
    if (/^(IMG|VIDEO|CANVAS|IFRAME|svg)$/.test(el.tagName)) return true;
    const m = cs(el).backgroundColor.match(/rgba?\(([^)]+)\)/);
    if (!m) return false;
    const p = m[1].split(/[ ,/]+/).filter(Boolean);
    return p.length < 4 || parseFloat(p[3]) >= 0.9;
  }
  // Карточки прижаты к краю горизонтальной ленты
  for (const sc of document.body.querySelectorAll('*')) {
    const s = cs(sc);
    if (!['auto', 'scroll', 'hidden'].includes(s.overflowX) || sc.scrollWidth <= sc.clientWidth + 4 || !shown(sc)) continue;
    const first = Array.from(sc.children).find(shown);
    if (!first) continue;
    const fs = cs(first);
    const card = parseFloat(fs.borderTopLeftRadius) > 0 || fs.boxShadow !== 'none' || parseFloat(fs.borderLeftWidth) > 0;
    const flush = first.getBoundingClientRect().left - sc.getBoundingClientRect().left - parseFloat(s.borderLeftWidth) < 1;
    const gutter = parseFloat(s.paddingRight) > 0 || parseFloat(s.columnGap) > 0 || parseFloat(fs.marginRight) > 0;
    if (card && flush && parseFloat(s.paddingLeft) === 0 && gutter && limit('edge-flush-cards', 3))
      add('edge-flush-cards', first, 'первая карточка вплотную к краю ленты, справа отступ есть');
  }
  // Первый экран: одна колонка уходит далеко вниз, соседняя умещается
  if (w >= 900) {
    const tops = Array.from(document.body.querySelectorAll('*')).filter((el) => {
      const r = el.getBoundingClientRect();
      return r.top < h * 0.5 && r.top >= -1 && shown(el) && el.children.length >= 2;
    });
    for (const el of tops) {
      const kids = Array.from(el.children).filter(shown);
      const rects = kids.map((k) => k.getBoundingClientRect());
      if (rects.length < 2 || rects.length > 4) continue;
      const side = rects.every((r) => Math.abs(r.top - rects[0].top) < 40) && new Set(rects.map((r) => Math.round(r.left / 50))).size === rects.length;
      if (!side) continue;
      const hs = rects.map((r) => r.height);
      if (Math.max(...hs) > 1.6 * h && Math.min(...hs) < 0.9 * h) {
        add('first-viewport-column-overflow', kids[hs.indexOf(Math.max(...hs))], `колонка ${Math.round(Math.max(...hs))}px при экране ${h}px, соседняя ${Math.round(Math.min(...hs))}px`);
        break;
      }
    }
  }
  return out;
}
