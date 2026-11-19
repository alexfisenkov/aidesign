// Сторож переходов внутри браузера — те же правила, что browser/guard.py:
// внутренний адрес (этот компьютер, локальная сеть, link-local и метаданные облака) — нельзя
// без allowLocal; путь, закрытый robots.txt своего хоста (RFC 9309), — нельзя без ownSite.
// Проверяется каждый запрос страницы, переходы главного фрейма — и каждый шаг редиректа.
import dns from 'node:dns/promises';
import net from 'node:net';

const AGENT = 'aidesign';
const UA = 'AIDesign/0.4 (+style reference; respects robots.txt)';
// Два отдельных списка: общий BlockList сверяет IPv4 и с правилами IPv6 (через ::ffff:0:0/96).
const block4 = new net.BlockList();
const block6 = new net.BlockList();
for (const [a, p] of [['0.0.0.0', 8], ['10.0.0.0', 8], ['100.64.0.0', 10], ['127.0.0.0', 8], ['169.254.0.0', 16],
  ['172.16.0.0', 12], ['192.0.0.0', 24], ['192.0.2.0', 24], ['192.168.0.0', 16], ['198.18.0.0', 15],
  ['198.51.100.0', 24], ['203.0.113.0', 24], ['224.0.0.0', 4], ['240.0.0.0', 4]]) block4.addSubnet(a, p, 'ipv4');
for (const [a, p] of [['::', 8], ['64:ff9b::', 96], ['100::', 64], ['2001:db8::', 32],
  ['fc00::', 7], ['fe80::', 10], ['ff00::', 8]]) block6.addSubnet(a, p, 'ipv6');

function v6groups(addr) {
  let a = addr;
  const dotted = /(\d+\.\d+\.\d+\.\d+)$/.exec(a);
  if (dotted) {
    const b = dotted[1].split('.').map(Number);
    a = a.slice(0, -dotted[1].length) + ((b[0] << 8) | b[1]).toString(16) + ':' + ((b[2] << 8) | b[3]).toString(16);
  }
  const [head, tail = null] = a.split('::');
  const h = head ? head.split(':') : [];
  const t = tail === null ? [] : (tail ? tail.split(':') : []);
  const fill = tail === null ? [] : Array(8 - h.length - t.length).fill('0');
  return [...h, ...fill, ...t].map((x) => parseInt(x || '0', 16));
}

export function internalIp(ip) {
  const addr = ip.split('%')[0];
  if (!net.isIPv6(addr)) return block4.check(addr, 'ipv4');
  const g = v6groups(addr);
  if (g.slice(0, 5).every((x) => x === 0) && (g[5] === 0 || g[5] === 0xffff)) {   // ::a.b.c.d и ::ffff:a.b.c.d
    const v4 = [g[6] >> 8, g[6] & 255, g[7] >> 8, g[7] & 255].join('.');
    return block4.check(v4, 'ipv4') || g[5] === 0;
  }
  return block6.check(addr, 'ipv6');
}

const hosts = new Map();
async function hostProblem(host) {
  const bare = host.replace(/^\[|\]$/g, '');
  if (!hosts.has(bare)) {
    hosts.set(bare, (async () => {
      let list;
      try { list = await dns.lookup(bare, { all: true, verbatim: true }); } catch { return `адрес ${bare} не находится`; }
      const bad = list.find((x) => internalIp(x.address));
      return bad ? `${bare} ведёт на внутренний адрес ${bad.address} (этот компьютер, локальная сеть или служебный адрес облака)` : null;
    })());
  }
  return hosts.get(bare);
}

// ── robots.txt ──────────────────────────────────────────────────────────────
function groups(text) {
  const out = [];
  let agents = [], rules = [], lastAgent = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.split('#')[0].trim();
    const i = line.indexOf(':');
    if (i < 0) continue;
    const key = line.slice(0, i).trim().toLowerCase(), value = line.slice(i + 1).trim();
    if (key === 'user-agent') {
      if (!lastAgent && (agents.length || rules.length)) { out.push([agents, rules]); agents = []; rules = []; }
      agents.push(value.toLowerCase());
      lastAgent = true;
    } else if (key === 'allow' || key === 'disallow') {
      lastAgent = false;
      if (agents.length && value) rules.push([key === 'allow', value]);
    }
  }
  if (agents.length) out.push([agents, rules]);
  return out;
}

const esc = (s) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
export function robotsAllows(text, url) {
  const gs = groups(text);
  const mine = gs.filter(([a]) => a.includes(AGENT));
  const rules = (mine.length ? mine : gs.filter(([a]) => a.includes('*'))).flatMap(([, r]) => r);
  const u = new URL(url);
  const target = decodeURIComponent(u.pathname || '/') + u.search;
  let best = null;
  for (const [allow, path] of rules) {
    let p = decodeURIComponent(path);
    const end = p.endsWith('$');
    if (end) p = p.slice(0, -1);
    const re = new RegExp('^' + p.split('*').map(esc).join('.*') + (end ? '$' : ''));
    if (re.test(target) && (!best || path.length > best[0] || (path.length === best[0] && allow))) best = [path.length, allow];
  }
  return !best || best[1];
}

const robotsCache = new Map();
async function robotsFor(origin, allowLocal) {
  if (!robotsCache.has(origin)) {
    robotsCache.set(origin, (async () => {
      let url = origin + '/robots.txt';
      for (let hop = 0; hop < 5; hop++) {
        const u = new URL(url);
        if (!allowLocal && await hostProblem(u.hostname)) return { state: 'unreachable' };
        let resp;
        try {
          resp = await fetch(url, { redirect: 'manual', headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(10000) });
        } catch { return { state: 'unreachable' }; }
        if (resp.status >= 300 && resp.status < 400 && resp.headers.get('location')) {
          url = new URL(resp.headers.get('location'), url).href;
          continue;
        }
        if (resp.status >= 400 && resp.status < 500) return { state: 'no-file' };
        if (resp.status >= 500) return { state: 'unreachable' };
        return { state: 'file', text: (await resp.text()).slice(0, 500 * 1024) };
      }
      return { state: 'unreachable' };
    })());
  }
  return robotsCache.get(origin);
}

// null — можно; иначе текст «почему нельзя».
export async function urlProblem(url, { allowLocal = false, ownSite = false, robots = true } = {}) {
  let u;
  try { u = new URL(url); } catch { return `странный адрес ${url}`; }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;   // data:, blob: — внутри страницы
  if (!allowLocal) {
    const why = await hostProblem(u.hostname);
    if (why) return `${why}: ${url}`;
  }
  if (!robots || ownSite) return null;
  const r = await robotsFor(u.origin, allowLocal);
  if (r.state === 'unreachable') return `robots.txt хоста ${u.host} не читается — по правилам это запрет: ${url}`;
  if (r.state === 'file' && !robotsAllows(r.text, url)) return `robots.txt запрещает этот адрес: ${url}`;
  return null;
}

// Подмена DNS: сторож проверил имя заранее, а браузер резолвит его заново и мог попасть на другой
// адрес. Поэтому у каждого ответа сверяем, с какого адреса он пришёл на самом деле (serverAddr).
// null — можно; иначе текст «почему нельзя». Нет адреса (ответ из кэша или наш fulfill) — нечего сверять.
export function answerProblem(addr, url, { allowLocal = false } = {}) {
  if (allowLocal || !addr || !addr.ipAddress || !internalIp(addr.ipAddress)) return null;
  let host = url;
  try { host = new URL(url).host; } catch {}
  return `${host} ответил с внутреннего адреса ${addr.ipAddress} (этот компьютер, локальная сеть или служебный адрес облака) — похоже на подмену DNS, снятие остановлено: ${url}`;
}

// Ставит сторожа на контекст браузера. stop.reason — первая причина остановки.
export async function guardContext(ctx, page, opts, stop) {
  ctx.on('response', async (resp) => {
    let addr = null;
    try { addr = await resp.serverAddr(); } catch {}
    const why = answerProblem(addr, resp.url(), opts);
    if (why && !stop.reason) stop.reason = why;
  });
  await ctx.route('**/*', async (route) => {
    const req = route.request();
    let main = false;
    try { main = req.isNavigationRequest() && req.frame() === page.mainFrame(); } catch {}
    const why = await urlProblem(req.url(), { ...opts, robots: main });
    if (why) {
      if (main && !stop.reason) stop.reason = why;
      return route.abort('blockedbyclient').catch(() => {});
    }
    if (!main) return route.continue().catch(() => {});
    // Переход главного фрейма: забираем сами без редиректов и проверяем, куда ведёт каждый шаг.
    let resp;
    try { resp = await route.fetch({ maxRedirects: 0 }); } catch { return route.abort().catch(() => {}); }
    const loc = resp.headers()['location'];
    if (resp.status() >= 300 && resp.status() < 400 && loc) {
      const next = new URL(loc, req.url()).href;
      const whyNext = await urlProblem(next, { ...opts, robots: true });
      if (whyNext) {
        if (!stop.reason) stop.reason = whyNext;
        return route.abort('blockedbyclient').catch(() => {});
      }
    }
    return route.fulfill({ response: resp }).catch(() => {});
  });
}
