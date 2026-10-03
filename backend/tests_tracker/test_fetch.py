"""fetch-guardrails during the request, and HTML-to-text extraction."""

import httpx
import pytest
import respx

from tests_tracker.conftest import PUBLIC_IP, resolver_for
from tracker.fetch import FetchError, extract, fetch_page
from tracker.guard import Blocked

PAGE = b"""<!doctype html><html><head><title> Robot Model Released </title>
<style>body { color: red }</style><script>alert('x')</script></head>
<body><nav>Home | About</nav><article><h1>Big news</h1><p>A new open model.</p></article>
<form><input name=q></form><footer>Copyright</footer></body></html>"""

HTML = {"content-type": "text/html; charset=utf-8"}


def fetch(url, policy, resolver=None, **kwargs):
    return fetch_page(url, policy.fetch, resolver=resolver or resolver_for(PUBLIC_IP), **kwargs)


def test_extract_drops_boilerplate():
    title, text = extract(PAGE)
    assert title == "Robot Model Released"
    assert "Big news" in text
    assert "A new open model." in text
    for gone in ("alert", "color: red", "Home | About", "Copyright"):
        assert gone not in text


def test_extract_og_title_fallback():
    title, _ = extract(b'<html><head><meta property="og:title" content="OG Title"></head></html>')
    assert title == "OG Title"


@respx.mock
def test_connects_to_vetted_ip_with_host_header(policy):
    route = respx.get(f"https://{PUBLIC_IP}/news").respond(200, headers=HTML, content=PAGE)
    # A second lookup would answer 127.0.0.1; only the first, vetted answer is used.
    page = fetch("https://news.example.com/news", policy, resolver_for(PUBLIC_IP, "127.0.0.1"))
    assert page.title == "Robot Model Released"
    request = route.calls.last.request
    assert request.headers["host"] == "news.example.com"
    assert request.extensions["sni_hostname"] == "news.example.com"


@respx.mock
def test_redirect_to_localhost_blocked(policy):
    respx.get(f"https://{PUBLIC_IP}/start").respond(
        302, headers={"location": "http://localhost/admin"}
    )
    resolver = resolver_for(PUBLIC_IP, "127.0.0.1")
    with pytest.raises(Blocked) as err:
        fetch("https://news.example.com/start", policy, resolver)
    assert err.value.reason == "blocked_address"


@respx.mock
def test_redirect_to_metadata_literal_blocked(policy):
    respx.get(f"https://{PUBLIC_IP}/start").respond(
        301, headers={"location": "http://169.254.169.254/latest/meta-data/"}
    )
    with pytest.raises(Blocked) as err:
        fetch("https://news.example.com/start", policy)
    assert err.value.reason == "blocked_address"


@respx.mock
def test_redirect_followed_and_rechecked(policy):
    respx.get(f"https://{PUBLIC_IP}/old").respond(302, headers={"location": "/new"})
    respx.get(f"https://{PUBLIC_IP}/new").respond(200, headers=HTML, content=PAGE)
    page = fetch("https://news.example.com/old", policy)
    assert page.final_url == "https://news.example.com/new"
    assert page.redirects == 1


@respx.mock
def test_too_many_redirects(policy):
    respx.get(url__regex=rf"https://{PUBLIC_IP}/loop\d*").mock(
        side_effect=lambda request: httpx.Response(
            302, headers={"location": request.url.path + "1"}
        )
    )
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/loop", policy)
    assert err.value.reason == "too_many_redirects"


@respx.mock
def test_streamed_body_cut_at_limit(policy):
    def chunks():
        for _ in range(100):
            yield b"x" * 1000

    respx.get(f"https://{PUBLIC_IP}/huge").respond(200, headers=HTML, content=chunks())
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/huge", policy)
    assert err.value.reason == "too_large"


@respx.mock
def test_content_length_rejected_before_reading(policy):
    respx.get(f"https://{PUBLIC_IP}/big").respond(
        200, headers={**HTML, "content-length": str(policy.fetch.max_bytes + 1)}, content=b"x"
    )
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/big", policy)
    assert err.value.reason == "too_large"


@respx.mock
def test_unsupported_content_type(policy):
    respx.get(f"https://{PUBLIC_IP}/file.pdf").respond(
        200, headers={"content-type": "application/pdf"}, content=b"%PDF"
    )
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/file.pdf", policy)
    assert err.value.reason == "unsupported_content_type"


@respx.mock
def test_slow_server_times_out(policy):
    respx.get(f"https://{PUBLIC_IP}/slow").mock(side_effect=httpx.ReadTimeout("no data"))
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/slow", policy)
    assert err.value.reason == "timeout"


@respx.mock
def test_overall_deadline(policy):
    ticks = iter([0.0, 0.0, 100.0, 100.0])
    respx.get(f"https://{PUBLIC_IP}/trickle").respond(200, headers=HTML, content=PAGE)
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/trickle", policy, clock=lambda: next(ticks))
    assert err.value.reason == "timeout"


@respx.mock
def test_http_error_status(policy):
    respx.get(f"https://{PUBLIC_IP}/gone").respond(404)
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/gone", policy)
    assert err.value.reason == "http_error"


@respx.mock
def test_plain_text(policy):
    respx.get(f"https://{PUBLIC_IP}/notes.txt").respond(
        200, headers={"content-type": "text/plain"}, content=b"plain notes"
    )
    page = fetch("https://news.example.com/notes.txt", policy)
    assert page.text == "plain notes"
    assert page.title == "https://news.example.com/notes.txt"


@respx.mock
def test_conditional_headers_and_not_modified(policy):
    route = respx.get(f"https://{PUBLIC_IP}/board").respond(
        304, headers={"etag": '"v2"', "last-modified": "Wed, 01 Oct 2026 12:00:00 GMT"}
    )
    page = fetch(
        "https://news.example.com/board",
        policy,
        headers={"If-None-Match": '"v1"', "Host": "evil.example.com"},
    )
    request = route.calls.last.request
    assert request.headers["if-none-match"] == '"v1"'
    assert request.headers["host"] == "news.example.com"  # extra headers cannot replace Host
    assert page.status == 304
    assert page.text == ""
    assert page.etag == '"v2"'
    assert page.last_modified == "Wed, 01 Oct 2026 12:00:00 GMT"


@respx.mock
def test_validators_on_ok_page(policy):
    respx.get(f"https://{PUBLIC_IP}/news").respond(
        200, headers={**HTML, "etag": '"abc"'}, content=PAGE
    )
    assert fetch("https://news.example.com/news", policy).etag == '"abc"'


@respx.mock
def test_http_error_carries_status(policy):
    respx.get(f"https://{PUBLIC_IP}/gone").respond(410)
    with pytest.raises(FetchError) as err:
        fetch("https://news.example.com/gone", policy)
    assert err.value.reason == "http_error"
    assert err.value.status == 410
