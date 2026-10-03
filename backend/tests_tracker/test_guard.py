"""fetch-guardrails: URL checks before any connection."""

import pytest

from tests_tracker.conftest import PUBLIC_IP, resolver_for
from tracker.guard import Blocked, check, host_allowed, is_public, literal_ip


def never_resolve(*_args, **_kwargs):
    raise AssertionError("must not resolve")


def reason(url, policy, resolver=never_resolve):
    with pytest.raises(Blocked) as err:
        check(url, policy.fetch, resolver=resolver)
    return err.value.reason


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("file:///etc/passwd", "scheme_not_allowed"),
        ("ftp://example.com/x", "scheme_not_allowed"),
        ("gopher://example.com/", "scheme_not_allowed"),
        ("example.com/no-scheme", "scheme_not_allowed"),
        ("https://user:pw@example.com/", "invalid_url"),
        ("https://user@example.com/", "invalid_url"),
        ("https:///no-host", "invalid_url"),
        ("https://exa mple.com/", "invalid_url"),
        ("https://example.com:99999/", "invalid_url"),
        ("", "invalid_url"),
        ("http://127.0.0.1/", "blocked_address"),
        ("http://127.0.0.1:8000/", "blocked_address"),
        ("http://[::1]/", "blocked_address"),
        ("http://169.254.169.254/latest/meta-data/", "blocked_address"),
        ("http://2130706433/", "blocked_address"),
        ("http://0x7f000001/", "blocked_address"),
        ("http://0177.0.0.1/", "blocked_address"),
        ("http://127.1/", "blocked_address"),
        ("http://0.0.0.0/", "blocked_address"),
        ("http://10.1.2.3/", "blocked_address"),
        ("http://192.168.0.1/", "blocked_address"),
        ("http://100.64.0.1/", "blocked_address"),
        ("http://224.0.0.1/", "blocked_address"),
        ("http://[::ffff:127.0.0.1]/", "blocked_address"),
        ("http://[::ffff:169.254.169.254]/", "blocked_address"),
        ("http://[fe80::1]/", "blocked_address"),
        ("http://[fc00::1]/", "blocked_address"),
    ],
)
def test_rejected_before_any_lookup(url, expected, policy):
    assert reason(url, policy) == expected


def test_name_resolving_to_private_address(policy):
    assert reason("https://internal.example.com/", policy, resolver_for("10.0.0.5")) == (
        "blocked_address"
    )


def test_any_bad_address_blocks(policy):
    def mixed(host, port, type=0):
        return [
            (2, 1, 6, "", (PUBLIC_IP, port)),
            (2, 1, 6, "", ("127.0.0.1", port)),
        ]

    assert reason("https://mixed.example.com/", policy, mixed) == "blocked_address"


def test_host_outside_allowlist_not_resolved(make_policy):
    policy = make_policy(fetch={"allowed_hosts": ["*.example.com"]})
    assert reason("https://example.org/", policy) == "host_not_allowed"


def test_dns_failure(policy):
    import socket

    def fail(*_a, **_k):
        raise socket.gaierror("no such host")

    assert reason("https://nxdomain.example.com/", policy, fail) == "dns_error"


def test_public_host_passes_and_pins(policy):
    vetted = check("https://news.example.com/a?b=1", policy.fetch, resolver=resolver_for(PUBLIC_IP))
    assert vetted.ip == PUBLIC_IP
    assert vetted.pinned_url() == f"https://{PUBLIC_IP}/a?b=1"
    assert vetted.host_header() == "news.example.com"


def test_non_default_port_kept(policy):
    vetted = check("http://news.example.com:8080/", policy.fetch, resolver=resolver_for(PUBLIC_IP))
    assert vetted.pinned_url() == f"http://{PUBLIC_IP}:8080/"
    assert vetted.host_header() == "news.example.com:8080"


def test_host_patterns():
    assert host_allowed("a.example.com", ("*.example.com",))
    assert host_allowed("example.com", ("*.example.com",))
    assert not host_allowed("badexample.com", ("*.example.com",))
    assert not host_allowed("example.org", ("example.com",))
    assert host_allowed("anything.org", ("*",))


def test_literal_forms():
    assert str(literal_ip("2130706433")) == "127.0.0.1"
    assert str(literal_ip("0x7f.1")) == "127.0.0.1"
    assert literal_ip("example.com") is None
    assert literal_ip("cafe.be") is None


def test_is_public():
    import ipaddress

    assert is_public(ipaddress.ip_address(PUBLIC_IP))
    assert is_public(ipaddress.ip_address("2606:4700::1111"))
    assert not is_public(ipaddress.ip_address("2002:7f00:1::"))  # 6to4 wrapping 127.0.0.1
    assert not is_public(ipaddress.ip_address("64:ff9b::a00:1"))  # NAT64 wrapping 10.0.0.1
