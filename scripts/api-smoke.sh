#!/usr/bin/env bash
# End-to-end smoke test of the HTTP API against a running dev server
# (start it with scripts/start.sh). Exercises the health-check, user-auth,
# user-management and api-docs scenarios, and scans every response body for
# password hashes. Exits non-zero on the first failure.
#
# Requires: curl, jq, and the Docker Compose database (used via psql to
# inspect rows and to expire a session).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v jq >/dev/null || { echo "Error: jq is required (brew install jq)." >&2; exit 1; }

set -a
# shellcheck disable=SC1091
source .env
set +a

BASE="${API_URL:-http://localhost:3000}"
RUN="$(date +%s)$RANDOM"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

HASHES=() # stored account.password values, collected as users register
PASSES=0

sql() {
  docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAq -c "$1"
}

fail() {
  echo "FAIL: $*" >&2
  echo "  last response: $STATUS $(head -c 500 "$TMP/body")" >&2
  exit 1
}

ok() {
  PASSES=$((PASSES + 1))
  echo "  ok  $*"
}

# Rule 1: no response may contain a hash or a password-ish key.
scan_body() {
  local hash
  for hash in "${HASHES[@]+"${HASHES[@]}"}"; do
    if grep -qF -- "$hash" "$TMP/body"; then fail "response contains a stored password hash"; fi
  done
  # The OpenAPI document describes request bodies, which do have a `password`
  # field; it is still scanned for hash values above.
  if [ "${SKIP_KEY_SCAN:-}" != 1 ] && jq -e . "$TMP/body" >/dev/null 2>&1; then
    if jq -e '[.. | objects | keys[]] | any(. == "password" or . == "passwordHash" or . == "hash")' "$TMP/body" >/dev/null; then
      fail "response contains a password/passwordHash/hash key"
    fi
  fi
}

# req METHOD PATH [JSON_BODY] [extra curl args...]
# Sets STATUS; body in $TMP/body, headers in $TMP/headers.
req() {
  local method="$1" path="$2" body="${3-}"
  shift 3 2>/dev/null || shift $#
  local args=(-sS -X "$method" -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}')
  if [ -n "$body" ]; then args+=(-H 'Content-Type: application/json' --data-raw "$body"); fi
  STATUS="$(curl "${args[@]}" "$@" "$BASE$path")"
  scan_body
}

auth() { echo "Authorization: Bearer $1"; }

expect_status() { [ "$STATUS" = "$1" ] || fail "$2: expected $1, got $STATUS"; }
expect_code() {
  expect_status "$1" "$3"
  [ "$(jq -r '.error.code' "$TMP/body")" = "$2" ] || fail "$3: expected error.code $2"
  ok "$3 -> $1 $2"
}
expect_user_keys() {
  [ "$(jq -c "$1 | keys" "$TMP/body")" = '["createdAt","email","firstName","id","lastName","updatedAt"]' ] \
    || fail "user object keys are not exactly the allow-list"
}
is_uuid() { [[ "$1" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; }
collect_hashes() {
  local h
  while IFS= read -r h; do [ -n "$h" ] && HASHES+=("$h"); done < <(sql "select password from account where password is not null")
}

A_EMAIL="ada-$RUN@example.com"
B_EMAIL="bob-$RUN@example.com"
A_PASS="correct-horse-$RUN"
B_PASS="battery-staple-$RUN"

echo "== health-check"
req GET /healthz
expect_status 200 "GET /healthz"
[ "$(jq -c . "$TMP/body")" = '{"status":"ok"}' ] || fail "healthz body"
grep -qi '^content-type: application/json' "$TMP/headers" || fail "healthz content-type"
ok "GET /healthz -> 200 {status: ok}, JSON"
req GET /healthz "" -H "$(auth garbage)"
expect_status 200 "GET /healthz with a bad token"
ok "GET /healthz ignores credentials"

echo "== register"
req POST /api/auth/register "{\"email\":\"$A_EMAIL\",\"password\":\"$A_PASS\",\"firstName\":\"Ada\",\"lastName\":\"Lovelace\"}"
expect_status 201 "register A"
expect_user_keys .
A_ID="$(jq -r .id "$TMP/body")"
is_uuid "$A_ID" || fail "user id is not a UUID"
[ "$(jq -r '.email + "|" + .firstName + "|" + .lastName' "$TMP/body")" = "$A_EMAIL|Ada|Lovelace" ] || fail "register fields"
jq -e 'has("token") | not' "$TMP/body" >/dev/null || fail "register returned a token"
ok "register -> 201 user, UUID id, no token"
collect_hashes

[ "$(sql "select name from \"user\" where id = '$A_ID'")" = "Ada Lovelace" ] || fail "user.name not derived"
[ "$(sql "select count(*) from account where user_id = '$A_ID' and password is not null and password <> '$A_PASS'")" = "1" ] \
  || fail "expected exactly one account row with a hashed password"
[ "$(sql "select count(*) from information_schema.columns where table_name = 'user' and column_name like '%password%'")" = "0" ] \
  || fail "user table has a password column"
ok "DB: name derived, hash only on account"

UPPER_A="$(echo "$A_EMAIL" | tr '[:lower:]' '[:upper:]')"
req POST /api/auth/register "{\"email\":\"$UPPER_A\",\"password\":\"$A_PASS\",\"firstName\":\"X\",\"lastName\":\"Y\"}"
expect_code 409 EMAIL_TAKEN "register duplicate email (different case)"

BAD_EMAIL="bad-$RUN@example.com"
req POST /api/auth/register "{\"email\":\"$BAD_EMAIL\",\"password\":\"$A_PASS\",\"firstName\":\"Ada\"}"
expect_code 400 VALIDATION_ERROR "register missing lastName"
req POST /api/auth/register "{\"email\":\"not-an-email\",\"password\":\"$A_PASS\",\"firstName\":\"Ada\",\"lastName\":\"L\"}"
expect_code 400 VALIDATION_ERROR "register invalid email"
SEVEN="s3cr7x$((RANDOM % 10))"
req POST /api/auth/register "{\"email\":\"$BAD_EMAIL\",\"password\":\"$SEVEN\",\"firstName\":\"Ada\",\"lastName\":\"L\"}"
expect_code 400 VALIDATION_ERROR "register 7-char password"
if grep -qF -- "$SEVEN" "$TMP/body"; then fail "validation error echoes the password"; fi
ok "validation error does not echo the password"
req POST /api/auth/register "{\"email\":\"$BAD_EMAIL\",\"password\":\"$A_PASS\",\"firstName\":\"Ada\",\"lastName\":\"L\",\"id\":\"$A_ID\"}"
expect_code 400 VALIDATION_ERROR "register with extra id"
req POST /api/auth/register "{\"email\":\"$BAD_EMAIL\",\"password\":\"$A_PASS\",\"firstName\":\"Ada\",\"lastName\":\"L\",\"emailVerified\":true}"
expect_code 400 VALIDATION_ERROR "register with extra emailVerified"
[ "$(sql "select count(*) from \"user\" where email = '$BAD_EMAIL'")" = "0" ] || fail "invalid registration created a user"
ok "no user created by invalid registrations"

req POST /api/auth/register "{\"email\":\"$B_EMAIL\",\"password\":\"$B_PASS\",\"firstName\":\"Bob\",\"lastName\":\"Builder\"}"
expect_status 201 "register B"
B_ID="$(jq -r .id "$TMP/body")"
collect_hashes
ok "register B"

echo "== login"
req POST /api/auth/login '{not json'
expect_code 400 VALIDATION_ERROR "login malformed JSON"
req POST /api/auth/login "{\"email\":\"$A_EMAIL\",\"password\":\"wrong-password\"}"
expect_code 401 INVALID_CREDENTIALS "login wrong password"
cp "$TMP/body" "$TMP/wrong-password"
req POST /api/auth/login "{\"email\":\"nobody-$RUN@example.com\",\"password\":\"wrong-password\"}"
expect_code 401 INVALID_CREDENTIALS "login unknown email"
cmp -s "$TMP/body" "$TMP/wrong-password" || fail "unknown-email and wrong-password bodies differ"
ok "unknown email is indistinguishable from wrong password"

req POST /api/auth/login "{\"email\":\"$A_EMAIL\",\"password\":\"$A_PASS\"}"
expect_status 200 "login A"
A_TOKEN="$(jq -r .token "$TMP/body")"
[ -n "$A_TOKEN" ] && [ "$A_TOKEN" != null ] || fail "login returned no token"
expect_user_keys .user
if grep -qi '^set-cookie:' "$TMP/headers"; then fail "login sent Set-Cookie"; fi
ok "login -> 200 token + user, no Set-Cookie"

req POST /api/auth/login "{\"email\":\"$B_EMAIL\",\"password\":\"$B_PASS\"}"
expect_status 200 "login B"
B_TOKEN="$(jq -r .token "$TMP/body")"
ok "login B"

echo "== bearer auth (/api/auth/me)"
req GET /api/auth/me
expect_code 401 UNAUTHORIZED "me without Authorization"
req GET /api/auth/me "" -H "Authorization: Basic abc"
expect_code 401 UNAUTHORIZED "me with Basic"
req GET /api/auth/me "" -H "Authorization: Bearer"
expect_code 401 UNAUTHORIZED "me with bare Bearer"
req GET /api/auth/me "" -H "Authorization: Bearer    "
expect_code 401 UNAUTHORIZED "me with blank Bearer"
req GET /api/auth/me "" -H "$(auth not-a-real-token)"
expect_code 401 UNAUTHORIZED "me with garbage token"
req GET /api/auth/me "" -H "$(auth "${A_TOKEN:0:10}")"
expect_code 401 UNAUTHORIZED "me with truncated token"
req GET /api/auth/me "" -H "Cookie: better-auth.session_token=$A_TOKEN"
expect_code 401 UNAUTHORIZED "me with cookie only"

req GET /api/auth/me "" -H "$(auth "$A_TOKEN")"
expect_status 200 "me with A's token"
expect_user_keys .
[ "$(jq -r .id "$TMP/body")" = "$A_ID" ] || fail "me returned the wrong user"
ok "me -> 200 A"

req POST /api/auth/login "{\"email\":\"$A_EMAIL\",\"password\":\"$A_PASS\"}"
EXPIRED_TOKEN="$(jq -r .token "$TMP/body")"
sql "update session set expires_at = now() - interval '1 minute' where token = '$EXPIRED_TOKEN'" >/dev/null
req GET /api/auth/me "" -H "$(auth "$EXPIRED_TOKEN")"
expect_code 401 UNAUTHORIZED "me with expired token"

echo "== user-management"
RANDOM_UUID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
for m in GET PATCH DELETE; do
  body=""; [ "$m" = PATCH ] && body='{"firstName":"X"}'
  req "$m" "/api/users/$A_ID" "$body"
  expect_code 401 UNAUTHORIZED "$m own id without token"
  req "$m" "/api/users/$A_ID" "$body" -H "$(auth garbage)"
  expect_code 401 UNAUTHORIZED "$m own id with garbage token"
done

req GET "/api/users/$A_ID" "" -H "$(auth "$A_TOKEN")"
expect_status 200 "GET own user"
expect_user_keys .
ok "GET own user -> 200"

req GET "/api/users/$B_ID" "" -H "$(auth "$A_TOKEN")"
expect_code 404 NOT_FOUND "GET other user's id"
cp "$TMP/body" "$TMP/other"
req GET "/api/users/$RANDOM_UUID" "" -H "$(auth "$A_TOKEN")"
expect_code 404 NOT_FOUND "GET nonexistent id"
cmp -s "$TMP/body" "$TMP/other" || fail "nonexistent id and other user's id differ"
req GET "/api/users/not-a-uuid" "" -H "$(auth "$A_TOKEN")"
expect_code 404 NOT_FOUND "GET invalid UUID"
cmp -s "$TMP/body" "$TMP/other" || fail "invalid UUID and other user's id differ"
ok "other / nonexistent / invalid ids are identical 404s"

req PATCH "/api/users/$B_ID" '{"firstName":"Hacked"}' -H "$(auth "$A_TOKEN")"
expect_code 404 NOT_FOUND "PATCH other user's id"
req DELETE "/api/users/$B_ID" "" -H "$(auth "$A_TOKEN")"
expect_code 404 NOT_FOUND "DELETE other user's id"
[ "$(sql "select first_name from \"user\" where id = '$B_ID'")" = "Bob" ] || fail "B was modified or deleted"
ok "B untouched"

BEFORE_UPDATED="$(sql "select extract(epoch from updated_at) from \"user\" where id = '$A_ID'")"
req PATCH "/api/users/$A_ID" '{"firstName":"Augusta"}' -H "$(auth "$A_TOKEN")"
expect_status 200 "PATCH own firstName"
expect_user_keys .
[ "$(jq -r '.firstName + "|" + .lastName' "$TMP/body")" = "Augusta|Lovelace" ] || fail "PATCH result"
AFTER_UPDATED="$(sql "select extract(epoch from updated_at) from \"user\" where id = '$A_ID'")"
awk "BEGIN { exit !($AFTER_UPDATED > $BEFORE_UPDATED) }" || fail "updatedAt did not advance"
[ "$(sql "select name from \"user\" where id = '$A_ID'")" = "Augusta Lovelace" ] || fail "name not recomputed"
ok "PATCH own firstName -> 200, lastName kept, updatedAt later, name recomputed"

req PATCH "/api/users/$A_ID" '{}' -H "$(auth "$A_TOKEN")"
expect_code 400 VALIDATION_ERROR "PATCH empty body"
for body in '{"email":"new@example.com"}' '{"password":"x"}' "{\"id\":\"$RANDOM_UUID\"}"; do
  req PATCH "/api/users/$A_ID" "$body" -H "$(auth "$A_TOKEN")"
  expect_code 400 VALIDATION_ERROR "PATCH forbidden field $body"
done
[ "$(sql "select email || '|' || first_name from \"user\" where id = '$A_ID'")" = "$A_EMAIL|Augusta" ] || fail "A changed by forbidden PATCH"
ok "A unchanged by forbidden PATCHes"

req DELETE "/api/users/$A_ID" "" -H "$(auth "$A_TOKEN")"
expect_status 204 "DELETE own user"
[ ! -s "$TMP/body" ] || fail "204 response has a body"
[ "$(sql "select (select count(*) from \"user\" where id = '$A_ID') + (select count(*) from account where user_id = '$A_ID') + (select count(*) from session where user_id = '$A_ID')")" = "0" ] \
  || fail "user/account/session rows remain after delete"
ok "DELETE own user -> 204, rows cascaded"
req GET /api/auth/me "" -H "$(auth "$A_TOKEN")"
expect_code 401 UNAUTHORIZED "me after deletion"
req POST /api/auth/login "{\"email\":\"$A_EMAIL\",\"password\":\"$A_PASS\"}"
expect_code 401 INVALID_CREDENTIALS "login after deletion"

echo "== api-docs"
SKIP_KEY_SCAN=1 req GET /api/openapi.json
expect_status 200 "GET /api/openapi.json"
jq -e '.openapi | startswith("3.1")' "$TMP/body" >/dev/null || fail "openapi version"
[ "$(jq -S . "$TMP/body")" = "$(jq -S . openapi/openapi.json)" ] || fail "served document differs from openapi/openapi.json"
ok "served OpenAPI 3.1 document matches the committed file"
req GET /docs
expect_status 200 "GET /docs"
grep -qi '^content-type: text/html' "$TMP/headers" || fail "/docs is not HTML"
ok "GET /docs -> 200 HTML"

# Clean up B.
req DELETE "/api/users/$B_ID" "" -H "$(auth "$B_TOKEN")"
expect_status 204 "DELETE B (cleanup)"

echo
echo "All $PASSES checks passed."
