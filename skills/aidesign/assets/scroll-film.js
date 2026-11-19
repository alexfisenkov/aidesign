/* AI Design — движок «сайт как фильм»: прокрутка ведёт цепочку видеоклипов.
   По мотивам: oso95/scroll-world references/scrub-engine.js (MIT, © 2026 cyw) и
   MengTo/Skills scroll-world-storytelling (MIT, © 2026 Meng To). Изменено: написано заново.
   Основной путь — прямой <video src> (работает по file:// и по http с Range); fetch → Blob —
   только улучшение по http, когда сервер не даёт перематывать; Blob освобождается
   (revokeObjectURL), дальние клипы выгружаются; настоящий кроссфейд на стыках; без скрипта и
   при prefers-reduced-motion страница остаётся обычной (кадры и текст в потоке).

   Разметка: <section data-film> с <script type="application/json" class="sf-config"> и
   статьями .sf-beat (по одной на бит). Конфиг:
     { beats: [{ clip, clipMobile, still, stillMobile, scroll, linger }],
       connectors: [url|null] (длина beats-1; null — стык перетеканием),
       connectorsMobile: [...], beatScroll: 1.3, linkScroll: 0.9,
       crossfade: 0.12, blend: 0.4, blob: "auto"|"never" }
   Тема — переменные страницы --sf-bg, --sf-ink, --sf-accent. */
(function () {
  'use strict';
  const instances = [];
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
  const linger = (x, L) => { L = clamp(L); const c = x - 0.5; return (1 - L) * x + L * (4 * c * c * c + 0.5); };

  function css() {
    if (document.getElementById('sf-css')) return;
    const s = document.createElement('style');
    s.id = 'sf-css';
    s.textContent = [
      '.sf.sf-on{position:relative;display:block;padding:0;margin:0;max-width:none}',
      '.sf-on .sf-stage{position:sticky;top:0;height:100vh;height:100svh;overflow:hidden}',
      '.sf-on .sf-scenes{position:absolute;inset:0;z-index:0}',
      '.sf-on .sf-scene{position:absolute;inset:0;opacity:0}',
      '.sf-on .sf-scene img,.sf-on .sf-scene video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}',
      '.sf-on .sf-scene video{opacity:0}.sf-on .sf-scene.sf-painted video{opacity:1}',
      '.sf-on .sf-copy{position:absolute;inset:0;z-index:1;pointer-events:none}',
      '.sf-on .sf-copy::before{content:"";position:absolute;inset:auto 0 0 0;height:62%;' +
        'background:linear-gradient(0deg,color-mix(in srgb,var(--sf-bg,#111) 88%,transparent),transparent)}',
      '.sf-on .sf-copy .sf-beat{position:absolute;left:clamp(1.25rem,6vw,5rem);right:clamp(1.25rem,6vw,5rem);' +
        'bottom:calc(clamp(3rem,10vh,7rem) + env(safe-area-inset-bottom));max-width:36rem;margin:0;padding:0;' +
        'display:block;opacity:0}',
      '.sf-on .sf-copy .sf-beat img,.sf-on .sf-copy .sf-beat picture{display:none}',
    ].join('\n');
    document.head.appendChild(s);
  }

  function mount(root, given) {
    if (!root || root.scrollFilm) return root && root.scrollFilm;
    let cfg = given;
    if (!cfg) {
      const node = root.querySelector('script.sf-config');
      try { cfg = JSON.parse(node ? node.textContent : '{}'); } catch (e) { cfg = {}; }
    }
    const beats = cfg.beats || [];
    // Обычная страница остаётся как есть: просьба системы «меньше движения» или нечего крутить.
    if (!beats.length || matchMedia('(prefers-reduced-motion: reduce)').matches) {
      root.classList.add('sf-still');
      return null;
    }
    const coarse = matchMedia('(hover: none) and (pointer: coarse)').matches;
    const phoneMQ = matchMedia('(max-width: 860px)');
    const phone = () => coarse || phoneMQ.matches;
    const http = /^https?:$/.test(location.protocol);
    const links = cfg.connectors || [], linksM = cfg.connectorsMobile || [];
    const stats = { blobs: 0, revoked: 0, unloaded: 0 };

    // Цепочка: бит 0, связка 0, бит 1, … Связки нет — соседние биты перетекают друг в друга.
    const segs = [];
    beats.forEach((b, i) => {
      segs.push({ kind: 'beat', bi: i, clip: b.clip, clipM: b.clipMobile, still: b.still, stillM: b.stillMobile,
                  w: b.scroll || cfg.beatScroll || 1.3, linger: b.linger || 0 });
      if (i < beats.length - 1 && links[i]) {
        segs.push({ kind: 'link', bi: i, clip: links[i], clipM: linksM[i], still: null, stillM: null,
                    w: cfg.linkScroll || 0.9, linger: 0 });
      }
    });
    segs.forEach((s, k) => {
      const next = segs[k + 1];
      const band = !next ? 0 : (s.kind === 'beat' && next.kind === 'beat') ? (cfg.blend ?? 0.4) : (cfg.crossfade ?? 0.12);
      s.fadeOut = band; if (next) next.fadeIn = band;
    });
    segs[0].fadeIn = 0;

    css();
    const stage = document.createElement('div'); stage.className = 'sf-stage';
    const scenes = document.createElement('div'); scenes.className = 'sf-scenes';
    const copy = document.createElement('div'); copy.className = 'sf-copy';
    const articles = Array.from(root.querySelectorAll('.sf-beat'));
    stage.append(scenes, copy);
    root.insertBefore(stage, root.firstChild);
    articles.forEach((a) => copy.appendChild(a));
    root.classList.add('sf-on');

    segs.forEach((s, k) => {
      const scene = document.createElement('div'); scene.className = 'sf-scene'; scene.style.zIndex = String(k + 1);
      // Постер грузится вместе со своим отрезком (load), а не все сразу.
      s.poster = (phone() && s.stillM) || s.still;
      if (s.poster) { s.img = document.createElement('img'); s.img.alt = ''; s.img.decoding = 'async'; scene.appendChild(s.img); }
      const v = document.createElement('video');
      v.muted = true; v.playsInline = true; v.preload = 'none';
      v.setAttribute('muted', ''); v.setAttribute('playsinline', ''); v.setAttribute('aria-hidden', 'true');
      scene.appendChild(v); scenes.appendChild(scene);
      Object.assign(s, { el: scene, video: v, loaded: false, ready: false, blob: null, url: null,
                         cur: 0, target: 0, op: 0, start: 0, end: 0 });
      v.addEventListener('loadedmetadata', () => {
        s.ready = true;
        const sk = v.seekable;
        const broken = !sk.length || sk.end(sk.length - 1) < (v.duration || 0) * 0.5;
        if (broken && http && cfg.blob !== 'never' && !s.blob) upgrade(s);
        v.currentTime = Math.max(0.001, s.cur * (v.duration || 0));
        kick();
      });
      v.addEventListener('seeked', () => { scene.classList.add('sf-painted'); kick(); });
      v.addEventListener('loadeddata', () => { if (!coarse) scene.classList.add('sf-painted'); if (primed) prime(v); });
      v.addEventListener('error', () => { if (s.blob && s.url) { drop(s); v.src = s.url; } });
    });

    function upgrade(s) {
      const url = s.url;
      fetch(url).then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
        .then((b) => {
          if (!s.loaded || s.url !== url) return;
          s.blob = URL.createObjectURL(b); stats.blobs++;
          s.ready = false; s.video.src = s.blob;
        }).catch(() => {});                                   // остаётся прямой src
    }
    function drop(s) { if (s.blob) { URL.revokeObjectURL(s.blob); s.blob = null; stats.revoked++; } }
    function load(s) {
      if (s.img && !s.img.getAttribute('src')) s.img.src = s.poster;
      if (s.loaded || !s.clip) return;
      s.loaded = true; s.url = (phone() && s.clipM) || s.clip;
      s.video.preload = 'auto'; s.video.src = s.url;
    }
    function unload(s) {
      if (!s.loaded) return;
      s.loaded = false; s.ready = false; s.url = null;
      s.video.pause(); s.video.removeAttribute('src'); s.video.load();
      drop(s); stats.unloaded++;
      s.el.classList.remove('sf-painted');
    }

    let vh = innerHeight, width = innerWidth, total = 0;
    function layout() {
      vh = innerHeight; width = innerWidth;
      let off = 0;
      segs.forEach((s) => { s.start = off * vh; off += s.w; s.end = off * vh; });
      total = off;
      root.style.height = (total * vh + vh) + 'px';
      read();
    }
    const progressY = () => clamp(-root.getBoundingClientRect().top, 0, total * vh);

    function read() {
      const y = progressY();
      segs.forEach((s) => {
        const fi = s.fadeIn * vh, fo = s.fadeOut * vh;
        const local = clamp((y - s.start) / (s.end - s.start));
        s.target = s.linger ? linger(local, s.linger) : local;
        let op = fi ? smooth((y - (s.start - fi / 2)) / fi) : (y >= s.start - 1 ? 1 : 0);
        if (fo && y > s.end + fo / 2) op = 0;
        s.op = op; s.el.style.opacity = op.toFixed(3);
        // Соседи — за экран до стыка; дальше полутора экранов — выгрузка (на телефоне в памяти 2–3 ролика).
        const near = y > s.start - vh && y < s.end + vh;
        const far = y < s.start - 1.5 * vh || y > s.end + 1.5 * vh;
        if (near) load(s); else if (far) unload(s);
      });
      articles.forEach((a, i) => {
        const s = segs.find((x) => x.kind === 'beat' && x.bi === i);
        const pr = clamp((y - s.start) / (s.end - s.start));
        const before = y < s.start, after = y > s.end;
        let o;
        if (i === 0) o = after ? 0 : smooth(1 - pr / 0.62);
        else if (i === articles.length - 1) o = before ? 0 : smooth(pr / 0.4);
        else o = before || after ? 0 : smooth(1 - Math.abs(pr - 0.5) / 0.5);
        a.style.opacity = o.toFixed(3);
        // Подпись погасла, но не выпала из потока чтения: экранный диктор и поиск по странице её
        // находят (без inert); фокус клавиатуры внутри неё прокручивает к её сцене (focusin ниже).
        a.style.pointerEvents = o > 0.5 ? 'auto' : 'none';
      });
      kick();
    }

    // Tab до ссылки в погасшей подписи — прокрутка к месту, где эта подпись видна целиком.
    articles.forEach((a, i) => a.addEventListener('focusin', () => {
      if (parseFloat(a.style.opacity) >= 0.5) return;
      const s = segs.find((x) => x.kind === 'beat' && x.bi === i);
      const at = i === 0 ? 0 : i === articles.length - 1 ? 1 : 0.5;
      window.scrollTo(0, root.getBoundingClientRect().top + window.scrollY + s.start + (s.end - s.start) * at);
    }));

    let looping = false;
    function kick() { if (!looping) { looping = true; requestAnimationFrame(tick); } }
    function tick() {
      const eps = phone() ? 0.03 : 1 / 60;
      let busy = false;
      segs.forEach((s) => {
        const d = s.target - s.cur;
        s.cur = Math.abs(d) < 0.001 ? s.target : s.cur + d * 0.25;
        if (s.cur !== s.target) busy = true;
        const v = s.video;
        if (!s.ready || !v.duration || s.op <= 0) return;
        if (v.seeking) { busy = true; return; }                // новая перемотка — только после seeked
        const t = clamp(s.cur, 0, 1) * Math.max(0, v.duration - 0.04);
        if (Math.abs(v.currentTime - t) > eps) { v.currentTime = t; busy = true; }
      });
      if (busy) requestAnimationFrame(tick); else looping = false;
    }

    // iPhone: бесшумное видео, которое ни разу не играло, может не показать кадр — будим касанием.
    let primed = false;
    function prime(v) { if (!phone() || !v.src) return; const p = v.play(); if (p && p.then) p.then(() => v.pause()).catch(() => {}); }
    const wake = () => { if (primed) return; primed = true; segs.forEach((s) => s.loaded && prime(s.video)); };
    addEventListener('pointerdown', wake, { once: true, passive: true });
    addEventListener('touchstart', wake, { once: true, passive: true });
    addEventListener('scroll', read, { passive: true });
    addEventListener('resize', () => { if (coarse && innerWidth === width) return; layout(); });  // адресная строка — не повод
    addEventListener('orientationchange', layout);
    addEventListener('load', layout);
    layout();

    const top = () => root.getBoundingClientRect().top + window.scrollY;
    const api = {
      root, stats,
      seams: () => segs.slice(0, -1).map((s, k) => ({ i: k + 1, y: Math.round(top() + s.end), band: Math.round(s.fadeOut * vh),
                                                     from: s.kind, to: segs[k + 1].kind })),
      state: () => segs.map((s, k) => ({ k, kind: s.kind, beat: s.bi, loaded: s.loaded, ready: s.ready, op: s.op,
                                         target: s.target, time: s.video.currentTime, duration: s.video.duration || 0,
                                         seeking: s.video.seeking, blob: !!s.blob,
                                         seekableEnd: s.video.seekable.length ? s.video.seekable.end(0) : 0,
                                         src: s.video.currentSrc || '' })),
      settled: () => segs.every((s) => {
        if (s.op <= 0 || !s.clip) return true;
        if (!s.ready || s.video.seeking || s.video.readyState < 2) return false;
        const t = clamp(s.target, 0, 1) * Math.max(0, s.video.duration - 0.04);
        return Math.abs(s.cur - s.target) < 0.002 && Math.abs(s.video.currentTime - t) < 0.06;
      }),
    };
    root.scrollFilm = api; instances.push(api);
    return api;
  }

  window.ScrollFilm = { mount, instances };
  const auto = () => document.querySelectorAll('[data-film]').forEach((r) => mount(r));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auto); else auto();
})();
