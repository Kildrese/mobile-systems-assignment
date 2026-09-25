import hashlib

from app.security import dummy_verify, hash_password, new_token, token_hash, verify_password


def test_hash_and_verify():
    stored = hash_password("correct-horse")
    assert stored.startswith("$argon2id$")
    assert verify_password("correct-horse", stored)
    assert not verify_password("wrong-one", stored)


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_dummy_verify_does_not_raise():
    dummy_verify("anything")


def test_tokens_are_random_and_long():
    tokens = {new_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)


def test_token_hash_is_sha256_hex():
    assert token_hash("abc") == hashlib.sha256(b"abc").hexdigest()
