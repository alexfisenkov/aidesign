// Окно cookies: закрываем так, как закрыл бы посетитель, — только кнопкой «принять».
// Нажимается кнопка, только если (1) она внутри окна согласия и (2) её текст целиком — одно
// из слов согласия (ACCEPT_WORDS), без хвостов: «Принять приглашение», «OK, delete my account»
// — не согласие. Окно согласия — контейнер известной платформы (OneTrust, Cookiebot, Sourcepoint,
// TrustArc, Usercentrics, Didomi, Quantcast, Osano, CookieYes, Complianz, iubenda, Klaro, Borlabs)
// или диалог / прибитая к краю плашка / блок с cookie|consent в имени — с текстом про cookies
// и не во всю страницу; `html` и `body` окном не бывают. Кнопки форм вокруг окна, ссылки, уводящие
// с сайта, «отказаться», «настроить» — никогда.
// По мотивам dembrandt lib/extractors/consent.ts (MIT, © 2025 thevangelist / © 2026 Dembrandt):
// обход фреймов и открытых shadow-корней, контейнеры известных платформ, слова кнопок.
// Изменено: окно согласия обязательно, слово кнопки целиком, русские слова.

const PLATFORMS = [
  '#onetrust-consent-sdk', '#onetrust-banner-sdk', '.optanon-alert-box-wrapper', '#CybotCookiebotDialog',
  '[id^="sp_message_container"]', '.sp_message_container', '#truste-consent-track', '.truste_box_overlay',
  '#usercentrics-root', '#uc-banner', '#didomi-host', '.didomi-popup', '.qc-cmp2-container', '.qc-cmp2-summary',
  '.osano-cm-window', '.cky-consent-container', '.cmplz-cookiebanner', '#iubenda-cs-banner', '.klaro',
  '#BorlabsCookieBox', '.cc-window',
];
const GENERIC = ['[role="dialog"]', '[role="alertdialog"]', '[aria-modal="true"]', 'dialog',
  '[id*="cookie" i]', '[class*="cookie" i]', '[id*="consent" i]', '[class*="consent" i]', '[id*="gdpr" i]'];
// Слова согласия — кнопка совпадает целиком (регистр, пробелы и знаки по краям не важны).
export const ACCEPT_WORDS = [
  'accept', 'accept all', 'accept all cookies', 'accept cookies', 'accept and close', 'accept and continue',
  'allow', 'allow all', 'allow all cookies', 'allow cookies', 'agree', 'i agree', 'agree and close',
  'got it', 'ok', 'okay', 'understood', 'i understand', 'yes i agree',
  'принять', 'принять все', 'принять всё', 'принять cookie', 'принять cookies', 'принять куки',
  'принять все cookie', 'принять все cookies', 'принять и закрыть', 'принять и продолжить', 'принимаю',
  'согласен', 'согласна', 'я согласен', 'я согласна', 'согласиться', 'соглашаюсь', 'хорошо', 'понятно',
  'ок', 'окей', 'разрешить', 'разрешить все', 'разрешить всё',
];
const COOKIE = 'cookie|куки|consent|gdpr|согласие на|персональных данных';

export function normalizeLabel(text) {
  return String(text || '').toLowerCase().replace(/&/g, ' and ')
    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ');
}

export function isAccept(text) {
  return ACCEPT_WORDS.includes(normalizeLabel(text));
}

function dismissInFrame({ platforms, generic, words, cookieSrc, isMain }) {
  const cookie = new RegExp(cookieSrc, 'i');
  const norm = (t) => String(t || '').toLowerCase().replace(/&/g, ' and ')
    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ');
  const label = (el) => el.textContent || el.value || el.getAttribute('aria-label') || '';
  const visible = (el) => { try { return el.getClientRects().length > 0; } catch { return false; } };
  const leaves = (el) => {
    try {
      const a = el.closest('a[href]');
      const href = a ? a.getAttribute('href') : '';
      if (!href || href.startsWith('#') || /^javascript:/i.test(href)) return false;
      return new URL(href, location.href).origin !== location.origin;
    } catch { return false; }
  };
  const roots = [document];
  let budget = 4000;
  const walk = (root, depth) => {
    if (depth > 6) return;
    for (const el of Array.from(root.querySelectorAll('*'))) {
      if (budget-- <= 0) return;
      if (el.shadowRoot) { roots.push(el.shadowRoot); walk(el.shadowRoot, depth + 1); }
    }
  };
  try { walk(document, 0); } catch {}
  const text = (el) => String(el.innerText || el.textContent || '').slice(0, 3000);
  const vw = innerWidth || 1, vh = innerHeight || 1;
  const docH = Math.max(document.documentElement.scrollHeight, vh);
  // Во всю страницу — не окно: больше 60 % экрана по площади или почти вся высота документа.
  const wholePage = (el) => {
    if (el === document.documentElement || el === document.body) return true;
    const r = el.getBoundingClientRect();
    return (r.width * r.height) / (vw * vh) > 0.6 || r.height >= 0.9 * docH;
  };
  const found = [];
  const add = (el, known) => {
    if (!el || found.some((f) => f.el === el) || !visible(el)) return;
    if (!known && (wholePage(el) || !cookie.test(text(el)))) return;
    found.push({ el, known });
  };
  for (const root of roots) {
    for (const [list, known] of [[platforms, true], [generic, false]]) {
      for (const sel of list) {
        try { root.querySelectorAll(sel).forEach((el) => add(el, known)); } catch {}
      }
    }
    for (const el of Array.from(root.querySelectorAll('div, section, aside, footer')).slice(0, 3000)) {
      const p = getComputedStyle(el).position;
      if (p === 'fixed' || p === 'sticky') add(el, false);
    }
  }
  // Фрейм платформы согласия: весь его документ — окно, если в нём только оно.
  if (!isMain && document.body && cookie.test(text(document.body)) && text(document.body).length < 3000) {
    found.push({ el: document.body, known: true });
  }
  for (const { el: box } of found) {
    const cands = Array.from(box.querySelectorAll(
      'button, a[role="button"], [role="button"], input[type="submit"], input[type="button"]')).slice(0, 40);
    if (box.shadowRoot) cands.push(...Array.from(box.shadowRoot.querySelectorAll('button, [role="button"]')));
    for (const el of cands) {
      const raw = label(el);
      if (!words.includes(norm(raw)) || !visible(el) || leaves(el)) continue;
      const form = el.closest('form');
      if (form && !box.contains(form)) continue;                    // форма вокруг окна — не наша
      try {
        el.click();
        return { text: String(raw).trim().replace(/\s+/g, ' ').slice(0, 60), how: box.id ? '#' + box.id : box.tagName.toLowerCase() };
      } catch {}
    }
  }
  return null;
}

function within(ms, work) {
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve(null), ms);
    work.then((v) => { clearTimeout(t); resolve(v); }, () => { clearTimeout(t); resolve(null); });
  });
}

export async function dismissConsent(page) {
  const main = page.mainFrame();
  for (const frame of page.frames().slice(0, 12)) {
    const hit = await within(2500, frame.evaluate(dismissInFrame,
      { platforms: PLATFORMS, generic: GENERIC, words: ACCEPT_WORDS, cookieSrc: COOKIE, isMain: frame === main }));
    if (hit) return frame === main ? hit : { ...hit, frame: true };
  }
  return null;
}
