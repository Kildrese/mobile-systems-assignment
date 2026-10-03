"""Download one page within the guardrails and extract its readable text.

Each hop is checked by `guard.check()` and then requested at the vetted address, with
the original name in the `Host` header and as the TLS server name, so the certificate
is still verified against the real host. Redirects are followed by hand so every hop is
checked again. Time is bounded by connect and read timeouts plus an overall deadline,
and size by a streamed byte cap.
"""

import re
import socket
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from tracker.config import FetchSettings
from tracker.guard import Resolver, check

ALLOWED_TYPES = {"text/html", "application/xhtml+xml", "text/plain", "application/json"}
DROPPED_TAGS = ("script", "style", "noscript", "nav", "footer", "form", "svg", "iframe", "template")
USER_AGENT = "mobile-systems-tracker/0.1 (+https://github.com/kildrese/mobile-systems-assignment)"


class FetchError(Exception):
    def __init__(self, reason: str, detail: str, status: int | None = None) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.status = status  # the HTTP status, for `http_error`


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    title: str
    text: str
    content_type: str
    status: int
    redirects: int
    # Validators for conditional requests. A `304` page has empty text.
    etag: str | None = None
    last_modified: str | None = None


def extract(html: bytes | str, charset: str | None = None) -> tuple[str, str]:
    """Title and readable text of an HTML page, without scripts, styles and navigation."""
    soup = BeautifulSoup(
        html, "html.parser", from_encoding=charset if isinstance(html, bytes) else None
    )
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string
    else:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = str(og["content"])
    for tag in soup(DROPPED_TAGS):
        tag.decompose()
    lines = (re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n").splitlines())
    return " ".join(title.split()), "\n".join(line for line in lines if line)


def _media_type(header: str) -> tuple[str, str | None]:
    media, _, params = header.partition(";")
    match = re.search(r"charset=\"?([\w.-]+)", params, re.IGNORECASE)
    return media.strip().lower(), match.group(1) if match else None


def _decode(body: bytes, charset: str | None) -> str:
    try:
        return body.decode(charset or "utf-8", errors="replace").strip()
    except LookupError:  # unknown charset name
        return body.decode("utf-8", errors="replace").strip()


def fetch_page(
    url: str,
    cfg: FetchSettings,
    *,
    resolver: Resolver = socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
    clock=time.monotonic,
    allowed_hosts: tuple[str, ...] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Page:
    """Fetch a page. Raises `Blocked` for a guardrail and `FetchError` for anything else.

    `headers` adds request headers such as `If-None-Match`; they cannot replace `Host`.
    A `304 Not Modified` answer returns a `Page` with status 304 and no text.
    """
    extra = {k: v for k, v in (headers or {}).items() if k.lower() != "host"}
    deadline = clock() + cfg.deadline_seconds
    current = url
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False) as client:
        for hop in range(cfg.max_redirects + 1):
            vetted = check(current, cfg, resolver=resolver, allowed_hosts=allowed_hosts)
            remaining = deadline - clock()
            if remaining <= 0:
                raise FetchError("timeout", f"deadline of {cfg.deadline_seconds}s passed")
            timeout = httpx.Timeout(
                connect=min(cfg.connect_timeout, remaining),
                read=min(cfg.read_timeout, remaining),
                write=min(cfg.read_timeout, remaining),
                pool=min(cfg.connect_timeout, remaining),
            )
            request = client.build_request(
                "GET",
                vetted.pinned_url(),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                    **extra,
                    "Host": vetted.host_header(),
                },
                timeout=timeout,
                extensions={"sni_hostname": vetted.host} if vetted.scheme == "https" else {},
            )
            try:
                response = client.send(request, stream=True)
            except httpx.TimeoutException as err:
                raise FetchError("timeout", str(err) or "request timed out") from None
            except httpx.HTTPError as err:
                raise FetchError("connection_error", str(err) or type(err).__name__) from None
            try:
                if response.is_redirect and response.status_code != 304:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(
                            "http_error", f"HTTP {response.status_code} without Location"
                        )
                    current = urljoin(current, location)
                    continue
                return _read(response, url, current, hop, cfg, deadline, clock)
            finally:
                response.close()
    raise FetchError("too_many_redirects", f"more than {cfg.max_redirects} redirects")


def _read(
    response: httpx.Response,
    url: str,
    final_url: str,
    redirects: int,
    cfg: FetchSettings,
    deadline: float,
    clock,
) -> Page:
    etag = response.headers.get("etag")
    last_modified = response.headers.get("last-modified")
    if response.status_code == 304:
        return Page(url, final_url, final_url, "", "", 304, redirects, etag, last_modified)
    if response.status_code >= 400:
        raise FetchError("http_error", f"HTTP {response.status_code}", response.status_code)
    media, charset = _media_type(response.headers.get("content-type", ""))
    if media not in ALLOWED_TYPES:
        raise FetchError("unsupported_content_type", f"content type '{media or '(none)'}'")
    length = response.headers.get("content-length")
    if length and length.isdigit() and int(length) > cfg.max_bytes:
        raise FetchError("too_large", f"Content-Length {length} exceeds {cfg.max_bytes} bytes")

    body = bytearray()
    try:
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > cfg.max_bytes:
                raise FetchError("too_large", f"body exceeds {cfg.max_bytes} bytes")
            if clock() > deadline:
                raise FetchError("timeout", f"deadline of {cfg.deadline_seconds}s passed")
    except httpx.TimeoutException as err:
        raise FetchError("timeout", str(err) or "read timed out") from None
    except httpx.HTTPError as err:
        raise FetchError("connection_error", str(err) or type(err).__name__) from None

    if media in ("text/html", "application/xhtml+xml"):
        title, text = extract(bytes(body), charset)
    else:
        title, text = "", _decode(bytes(body), charset)
    return Page(
        url,
        final_url,
        title or final_url,
        text,
        media,
        response.status_code,
        redirects,
        etag,
        last_modified,
    )
