# Spec Delta

## Purpose

Stops `fetch_article` from becoming a server-side request forgery or resource-exhaustion vector. It checks scheme, host and resolved address before any connection, and bounds time and size during the download.

## ADDED Requirements

### Requirement: Scheme allowlist
`fetch_article` SHALL reject, before any DNS lookup or connection, any URL whose scheme is not in the policy's allowed schemes. Only `http` and `https` can be allowed. URLs that fail to parse, have no host, or carry credentials (`user:pass@`) SHALL also be rejected.

#### Scenario: File URL
- **WHEN** `fetch_article("file:///etc/passwd")` is called
- **THEN** it returns reason `scheme_not_allowed` and opens no file or connection

#### Scenario: Credentials in URL
- **WHEN** `fetch_article("https://user:pw@example.com/")` is called
- **THEN** it returns reason `invalid_url`

### Requirement: Host allowlist
`fetch_article` SHALL reject URLs whose host does not match the policy's allowed host patterns. Patterns are exact hostnames or `*.domain` suffixes. A single `*` allows any public host.

#### Scenario: Host outside policy
- **WHEN** policy allows only `*.greenhouse.io` and the URL host is `example.org`
- **THEN** it returns reason `host_not_allowed` without resolving the host

### Requirement: Non-public addresses are blocked
Before connecting, `fetch_article` SHALL resolve the host and reject the request if any resolved address is loopback, private, link-local, unspecified, multicast, reserved, shared (CGNAT) or otherwise not globally routable. IPv4-mapped IPv6 addresses SHALL be checked as their IPv4 form. Literal IP hosts, including decimal, octal and hex IPv4 forms, SHALL be checked the same way.

#### Scenario: Loopback literal
- **WHEN** `fetch_article("http://127.0.0.1/")` or `fetch_article("http://[::1]/")` is called
- **THEN** it returns reason `blocked_address`

#### Scenario: Cloud metadata address
- **WHEN** `fetch_article("http://169.254.169.254/latest/meta-data/")` is called
- **THEN** it returns reason `blocked_address`

#### Scenario: Name resolving to a private address
- **WHEN** a hostname resolves to `10.0.0.5`
- **THEN** it returns reason `blocked_address` and opens no connection

#### Scenario: Obfuscated loopback
- **WHEN** `fetch_article("http://2130706433/")` is called
- **THEN** it returns reason `blocked_address`

### Requirement: Connection is pinned to the vetted address
The connection SHALL go to the address that passed the check, not to a second lookup of the hostname. For https, the certificate SHALL still be verified against the original hostname.

#### Scenario: DNS rebinding
- **WHEN** a hostname resolves to a public address at check time and would resolve to `127.0.0.1` on a second lookup
- **THEN** the request still goes to the public address that was checked

### Requirement: Redirects are re-checked
Redirects SHALL be followed manually, up to a policy limit (default 5). Every hop SHALL pass the scheme, host and address checks again. Exceeding the limit SHALL return reason `too_many_redirects`.

#### Scenario: Redirect to internal host
- **WHEN** an allowed public URL answers `302 Location: http://localhost/admin`
- **THEN** the redirect is not followed, and the result has reason `blocked_address`

### Requirement: Timeout, size and type limits
Each request SHALL have connect and read timeouts from policy, plus an overall deadline. The body SHALL be streamed and cut off once it exceeds the policy's byte limit, returning reason `too_large`. A `Content-Length` above the limit SHALL be rejected before reading the body. Content types outside the allowlist (HTML, plain text, JSON) SHALL return reason `unsupported_content_type`.

#### Scenario: Huge response
- **WHEN** a page streams more bytes than `fetch.max_bytes`
- **THEN** reading stops at the limit and the result has reason `too_large`

#### Scenario: Slow server
- **WHEN** a server accepts the connection but sends nothing for longer than the read timeout
- **THEN** the fetch fails with reason `timeout` within the configured deadline
