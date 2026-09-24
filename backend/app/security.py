"""Password hashing and session tokens."""

import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# argon2id with argon2-cffi's defaults (64 MiB, 3 iterations, 4 lanes), above
# OWASP's minimums. Each hash gets its own random salt.
_hasher = PasswordHash((Argon2Hasher(),))

# Verified against when a login names an unknown user, so that path costs as
# much as a wrong password and response times don't reveal which users exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hash: str) -> bool:
    return _hasher.verify(password, hash)


def dummy_verify(password: str) -> None:
    _hasher.verify(password, _DUMMY_HASH)


def new_token() -> str:
    """256 random bits, URL-safe base64."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """SHA-256 (hex). A fast hash is fine: the input is random, not a password."""
    return hashlib.sha256(token.encode()).hexdigest()
