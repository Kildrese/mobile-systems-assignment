"""URL checks run before `fetch_article` opens any connection.

Order: parse, scheme, credentials, host pattern (no DNS yet), then resolution and the
address check. Every resolved address must be globally routable; the caller then
connects to the vetted address itself, never to a second lookup of the name.
"""

import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, replace
from urllib.parse import SplitResult, urlsplit

from tracker.config import FetchSettings

MAX_URL_LENGTH = 2048
DEFAULT_PORTS = {"http": 80, "https": 443}
_HOSTNAME = re.compile(r"[a-z0-9.-]+")
# Characters that can make up a numeric IPv4 form `inet_aton` accepts (2130706433, 0x7f.1).
_NUMERIC_HOST = re.compile(r"[0-9a-fx.]+")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[..., list]


class Blocked(Exception):
    """The URL failed a guardrail. `reason` is machine-readable."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Vetted:
    url: str
    scheme: str
    host: str
    port: int
    ip: str | None  # None when the check ran without resolution
    path: str

    def pinned_url(self) -> str:
        """The URL with the host replaced by the vetted address."""
        assert self.ip is not None
        host = f"[{self.ip}]" if ":" in self.ip else self.ip
        if self.port != DEFAULT_PORTS[self.scheme]:
            host += f":{self.port}"
        return f"{self.scheme}://{host}{self.path}"

    def host_header(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return host if DEFAULT_PORTS[self.scheme] == self.port else f"{host}:{self.port}"


def _split(url: str) -> SplitResult:
    if not url or len(url) > MAX_URL_LENGTH:
        raise Blocked("invalid_url", "URL is empty or longer than 2048 characters")
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise Blocked("invalid_url", "URL contains whitespace or control characters")
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises ValueError for a bad port
    except ValueError as err:
        raise Blocked("invalid_url", str(err)) from None
    return parts


def literal_ip(host: str) -> IPAddress | None:
    """Parse a host that is an IP literal, including decimal, octal and hex IPv4 forms."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if _NUMERIC_HOST.fullmatch(host) and any(ch.isdigit() for ch in host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


def _effective(ip: IPAddress) -> IPAddress:
    """The IPv4 address hidden inside an IPv6 one, where there is one."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip.sixtofour is not None:
            return ip.sixtofour
        if ip.teredo is not None:
            return ip.teredo[1]
        if ip in _NAT64:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def is_public(ip: IPAddress) -> bool:
    for candidate in {ip, _effective(ip)}:
        if (
            not candidate.is_global
            or candidate.is_private
            or candidate.is_loopback
            or candidate.is_link_local
            or candidate.is_multicast
            or candidate.is_reserved
            or candidate.is_unspecified
        ):
            return False
    return True


def host_allowed(host: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern == "*" or host == pattern:
            return True
        if pattern.startswith("*.") and (host == pattern[2:] or host.endswith(pattern[1:])):
            return True
    return False


def check(
    url: str,
    cfg: FetchSettings,
    *,
    resolver: Resolver = socket.getaddrinfo,
    resolve: bool = True,
    allowed_hosts: tuple[str, ...] | None = None,
) -> Vetted:
    """Check a URL against the guardrails. Raises `Blocked` with the reason.

    `allowed_hosts` narrows `cfg.allowed_hosts` for one agent: both must match.
    """
    parts = _split(url)
    scheme = parts.scheme.lower()
    if scheme not in cfg.allowed_schemes:
        raise Blocked("scheme_not_allowed", f"scheme '{scheme or '(none)'}' is not allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise Blocked("invalid_url", "URLs with credentials are not allowed")
    raw_host = (parts.hostname or "").rstrip(".")
    if not raw_host:
        raise Blocked("invalid_url", "URL has no host")
    try:
        host = raw_host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise Blocked("invalid_url", "host is not a valid domain name") from None

    ip = literal_ip(host)
    if ip is None and not _HOSTNAME.fullmatch(host):
        raise Blocked("invalid_url", f"host '{host}' is not a valid domain name")
    if ip is not None:
        host = str(ip)
    if allowed_hosts is not None and not host_allowed(host, allowed_hosts):
        raise Blocked("host_not_allowed", f"host '{host}' is not in this agent's fetch_hosts")
    if not host_allowed(host, cfg.allowed_hosts):
        raise Blocked("host_not_allowed", f"host '{host}' is not in fetch.allowed_hosts")

    port = parts.port or DEFAULT_PORTS[scheme]
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    vetted = Vetted(url=url, scheme=scheme, host=host, port=port, ip=None, path=path)
    if ip is not None:
        if not is_public(ip):
            raise Blocked("blocked_address", f"{ip} is not a public address")
        return replace(vetted, ip=str(ip))
    if not resolve:
        return vetted

    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as err:
        raise Blocked("dns_error", f"cannot resolve '{host}': {err}") from None
    addresses: list[IPAddress] = []
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise Blocked("dns_error", f"'{host}' resolved to no address")
    if bad := [str(a) for a in addresses if not is_public(a)]:
        raise Blocked("blocked_address", f"'{host}' resolves to non-public {', '.join(bad)}")
    # Prefer IPv4: many hosts (and this machine) lack working IPv6 routes.
    chosen = next((a for a in addresses if a.version == 4), addresses[0])
    return replace(vetted, ip=str(chosen))
