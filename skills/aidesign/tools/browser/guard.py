"""Сторож адресов для extract.py: внутренние адреса и robots.txt (RFC 9309).

Внутренний адрес — всё, что не «глобальный» адрес интернета после разрешения имени: этот
компьютер (127.0.0.0/8, ::1, localhost), локальная сеть (10/8, 172.16/12, 192.168/16, fc00::/7),
link-local и метаданные облака (169.254/16, fe80::/10), 100.64/10, 0.0.0.0, групповые. Такие
адреса открываются только с флагом человека. Тем же правилам следует browser/guard.mjs —
он проверяет каждый переход внутри браузера, в том числе редиректы.
"""

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

AGENT = "aidesign"
MAX_REDIRECTS = 5


def internal(ip) -> bool:
    ip = ipaddress.ip_address(ip.split("%", 1)[0]) if isinstance(ip, str) else ip
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped:
        ip = mapped
    return (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified)


def whatwg_ipv4(host: str):
    """Имя, которое браузер прочтёт как IPv4 (0177.0.0.1, 0x7f.1, 127.1, 2130706433), — точками; иначе None."""
    parts = host.rstrip(".").split(".")
    if not host or len(parts) > 4:
        return None
    nums = []
    for p in parts:
        try:
            if re.fullmatch(r"0[xX][0-9a-fA-F]*", p):
                nums.append(int(p[2:] or "0", 16))
            elif re.fullmatch(r"0[0-7]+", p):
                nums.append(int(p, 8))
            elif re.fullmatch(r"\d+", p):
                nums.append(int(p, 10))
            else:
                return None
        except ValueError:
            return None
    if any(n > 255 for n in nums[:-1]) or nums[-1] >= 256 ** (5 - len(nums)):
        return None
    value = nums[-1]
    for i, n in enumerate(nums[:-1]):
        value += n << (8 * (3 - i))
    return str(ipaddress.IPv4Address(value))


def canonical_url(url: str) -> str:
    """Адрес с хостом IPv4 в той записи, в какой его поймёт браузер."""
    p = urllib.parse.urlsplit(url)
    ip = whatwg_ipv4(p.hostname or "")
    if not ip or ip == p.hostname:
        return url
    netloc = ip + (":%d" % p.port if p.port else "")
    return urllib.parse.urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))


def address_problem(url: str):
    """None — адрес снаружи; иначе строка «почему нельзя»."""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        return "в адресе нет имени сайта"
    host = whatwg_ipv4(host) or host
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return "адрес %s не находится" % host
    for info in infos:
        addr = info[4][0]
        if internal(addr):
            return ("%s ведёт на внутренний адрес %s (этот компьютер, локальная сеть или служебный адрес "
                    "облака)" % (host, addr.split("%", 1)[0]))
    return None


# ── robots.txt ──────────────────────────────────────────────────────────────

def _groups(text: str):
    groups, agents, rules, last_was_agent = [], [], [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            last_was_agent = False
            if agents and value:
                rules.append((key == "allow", value))
    if agents:
        groups.append((agents, rules))
    return groups


def _pattern(path: str):
    end = path.endswith("$")
    body = re.escape(path[:-1] if end else path).replace(r"\*", ".*")
    return re.compile(body + ("$" if end else ""))


def robots_allows(text: str, url: str) -> bool:
    """Самое длинное совпадавшее правило; при равной длине — разрешение. Своя группа важнее «*»."""
    groups = _groups(text)
    mine = [r for a, r in groups if AGENT in a]
    rules = [x for r in (mine or [r for a, r in groups if "*" in a]) for x in r]
    p = urllib.parse.urlsplit(url)
    target = urllib.parse.unquote(p.path or "/") + ("?" + p.query if p.query else "")
    best = None
    for allow, path in rules:
        if _pattern(urllib.parse.unquote(path)).match(target):
            key = (len(path), allow)
            best = key if best is None or key > best else best
    return best is None or best[1]


class _NoInternalRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, allow_local):
        self.allow_local = allow_local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.allow_local and address_problem(newurl):
            raise urllib.error.URLError("redirect to internal address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def robots(url: str, ua: str, allow_local=False, timeout: float = 10) -> str:
    """allowed | disallowed | no-file | unreachable (RFC 9309: 4xx — правил нет, 5xx и сбой — нельзя)."""
    p = urllib.parse.urlsplit(url)
    opener = urllib.request.build_opener(_NoInternalRedirect(allow_local))
    req = urllib.request.Request("%s://%s/robots.txt" % (p.scheme, p.netloc), headers={"User-Agent": ua})
    try:
        with opener.open(req, timeout=timeout) as r:
            body = r.read(500 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return "no-file" if 400 <= e.code < 500 else "unreachable"
    except (urllib.error.URLError, OSError, ValueError):
        return "unreachable"
    return "allowed" if robots_allows(body, url) else "disallowed"
