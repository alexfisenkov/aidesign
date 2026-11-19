// Что читается со страницы: отрисованные стили элементов, переменные :root, @media, шрифты,
// снимки стиля кнопок, полей и ссылок. Функции выполняются внутри страницы (page.evaluate),
// поэтому каждая самодостаточна. Тексты страницы не забираются — только стили.

// Ставит window.__aidesign: перевод любого CSS-цвета в #rrggbb[aa] через пиксель холста
// (так приводятся и oklch, и color(display-p3)) и снимок стиля элемента.
export function installHelpers() {
  if (window.__aidesign) return;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const cache = new Map();
  const two = (n) => n.toString(16).padStart(2, '0');
  const hex = (c) => {
    if (!c || c === 'transparent' || c === 'none') return null;
    if (cache.has(c)) return cache.get(c);
    let out = null;
    try {
      cx.clearRect(0, 0, 1, 1);
      cx.fillStyle = 'rgba(0,0,0,0)';
      cx.fillStyle = c;
      cx.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = cx.getImageData(0, 0, 1, 1).data;
      out = a === 0 ? null : '#' + two(r) + two(g) + two(b) + (a < 250 ? two(a) : '');
    } catch {}
    cache.set(c, out);
    return out;
  };
  const snap = (el) => {
    const s = getComputedStyle(el);
    const bw = parseFloat(s.borderTopWidth) || 0;
    const ow = parseFloat(s.outlineWidth) || 0;
    return {
      bg: hex(s.backgroundColor), color: hex(s.color),
      border: `${s.borderTopWidth} ${s.borderTopStyle}`, borderColor: bw ? hex(s.borderTopColor) : null,
      radius: s.borderTopLeftRadius, padding: `${s.paddingTop} ${s.paddingRight}`,
      fs: parseFloat(s.fontSize), fw: s.fontWeight, ff: s.fontFamily,
      shadow: s.boxShadow === 'none' ? null : s.boxShadow,
      outline: `${s.outlineWidth} ${s.outlineStyle}`, outlineColor: ow && s.outlineStyle !== 'none' ? hex(s.outlineColor) : null,
      decoration: s.textDecorationLine, transition: s.transition,
    };
  };
  window.__aidesign = { hex, snap };
}

export function collectPage(limit) {
  const { hex } = window.__aidesign;
  const skip = new Set(['SCRIPT', 'STYLE', 'META', 'LINK', 'NOSCRIPT', 'TEMPLATE', 'HEAD', 'TITLE', 'BR']);
  const els = [];
  let total = 0;
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (skip.has(el.tagName) || el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none') continue;
    total++;
    if (els.length >= limit) continue;
    const cls = typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal) || '';
    const tag = el.tagName.toLowerCase();
    const ctx = `${tag} ${cls} ${el.id || ''} ${el.getAttribute('role') || ''}`.toLowerCase().slice(0, 200);
    const text = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
    const px = (v) => parseFloat(v) || 0;
    // Заливка градиентом (частая у кнопок): берём средний цвет из его точек.
    let bg = hex(s.backgroundColor);
    if (!bg && /gradient\(/.test(s.backgroundImage)) {
      const stops = (s.backgroundImage.match(/(rgba?|oklch|oklab|lab|lch|color)\([^()]*\)|#[0-9a-f]{3,8}\b/gi) || [])
        .map(hex).filter((c) => c && c.length === 7);
      if (stops.length) bg = stops[Math.floor(stops.length / 2)];
    }
    // Логотип: цвет заливки знака (svg) в ссылке на главную или в блоке с «logo» в имени.
    let fill = null;
    let logo = false;
    if (tag === 'svg') {
      logo = !!el.closest('[class*="logo" i], [id*="logo" i], [aria-label*="logo" i], [aria-label*="home" i], ' +
        '[aria-label*="главн" i], a[href="/"]');
      const shape = el.querySelector('path, circle, rect, polygon, ellipse');
      fill = shape ? hex(getComputedStyle(shape).fill) : hex(s.fill);
    }
    els.push({
      tag, ctx, area: Math.min(rect.width * rect.height, 4e6), text, fill, logo,
      color: text ? hex(s.color) : null, bg,
      border: px(s.borderTopWidth) && s.borderTopStyle !== 'none' ? hex(s.borderTopColor) : null,
      ff: s.fontFamily, fs: px(s.fontSize), fw: s.fontWeight, lh: s.lineHeight,
      radius: s.borderTopLeftRadius, shadow: s.boxShadow === 'none' ? null : s.boxShadow,
      pad: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(px),
      mar: [s.marginTop, s.marginRight, s.marginBottom, s.marginLeft].map(px),
      gap: s.display.includes('flex') || s.display.includes('grid') ? [px(s.rowGap), px(s.columnGap)] : [],
      td: s.transitionDuration, tt: s.transitionTimingFunction, ad: s.animationDuration, at: s.animationTimingFunction,
    });
  }
  const vars = [];
  const media = [];
  const rootStyle = getComputedStyle(document.documentElement);
  const visit = (rules) => {
    for (const r of rules) {
      if (r.media && r.conditionText !== undefined) media.push(r.conditionText);
      if (r.cssRules) { try { visit(r.cssRules); } catch {} }
      if (r.style && /(^|,)\s*(:root|html)\s*(,|$)/.test(r.selectorText || '')) {
        for (const name of Array.from(r.style)) {
          if (!name.startsWith('--') || vars.length >= 400) continue;
          const value = rootStyle.getPropertyValue(name).trim();
          const isColor = /^(#|rgb|hsl|hwb|lab|lch|oklab|oklch|color\()/i.test(value);
          vars.push({ name, value: value.slice(0, 120), hex: isColor ? hex(value) : null });
        }
      }
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    try { visit(sheet.cssRules); } catch {}               // чужой домен без CORS — читаем из ответа сети
  }
  const body = document.body || document.documentElement;
  let bg = null;
  for (let n = body; n && !bg; n = n.parentElement) {
    const c = hex(getComputedStyle(n).backgroundColor);
    if (c && (c.length === 7 || parseInt(c.slice(7), 16) >= 230)) bg = c.slice(0, 7);
  }
  const fonts = [];
  try { document.fonts.forEach((f) => { if (f.status === 'loaded') fonts.push(f.family.replace(/["']/g, '')); }); } catch {}
  return {
    total, elements: els, vars, media, fonts: Array.from(new Set(fonts)),
    body: { bg: bg || '#ffffff', color: (hex(getComputedStyle(body).color) || '#000000').slice(0, 7) },
  };
}

// Подпись стиля — чтобы снимать состояния только у разных по виду кнопок и полей.
export function signature(el) {
  const s = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  if (r.width < 1 || r.height < 1 || s.visibility === 'hidden') return null;
  return [s.backgroundColor, s.color, s.borderTopLeftRadius, s.borderTopColor, s.textDecorationLine].join('|');
}
