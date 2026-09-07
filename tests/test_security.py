from datetime import UTC, datetime
from uuid import uuid4

import pytest
from jose import jwt
from shared.auth import create_access_token, create_refresh_token, decode_token
from shared.exceptions import AuthenticationError


def issue(keys, **kwargs):
    return create_access_token(str(uuid4()), "user@example.com", keys[0], **kwargs)


def test_asymmetric_claims_and_public_verification(keys):
    token = issue(keys, scopes=["documents:read"])
    payload = decode_token(token, keys[1])
    assert payload.scope == "documents:read"
    assert payload.jti
    assert payload.iss == "http://localhost"
    assert payload.aud == "ai-platform"
    assert jwt.get_unverified_header(token)["kid"]


@pytest.mark.parametrize("kind", ["access", "refresh"])
def test_repeated_issuance_is_unique(keys, kind):
    factory = create_access_token if kind == "access" else create_refresh_token
    args = (str(uuid4()), "user@example.com", keys[0])
    assert factory(*args) != factory(*args)


@pytest.mark.parametrize(
    "claim,value",
    [
        ("iss", "https://other.example"),
        ("aud", "other-resource"),
        ("exp", 1),
        ("iat", 9999999999),
        ("sub", "not-a-uuid"),
        ("scope", ["documents:read"]),
        ("jti", ""),
    ],
)
def test_invalid_claims_rejected(keys, claim, value):
    token = issue(keys)
    raw = jwt.get_unverified_claims(token)
    raw[claim] = value
    forged = jwt.encode(raw, keys[0], algorithm="RS256", headers=jwt.get_unverified_header(token))
    with pytest.raises(AuthenticationError):
        decode_token(forged, keys[1])


@pytest.mark.parametrize(
    "claim", ["exp", "iat", "iss", "aud", "sub", "email", "type", "jti", "scope"]
)
def test_missing_claim_rejected(keys, claim):
    token = issue(keys)
    raw = jwt.get_unverified_claims(token)
    del raw[claim]
    token = jwt.encode(raw, keys[0], algorithm="RS256", headers=jwt.get_unverified_header(token))
    with pytest.raises(AuthenticationError):
        decode_token(token, keys[1])


def test_altered_signature_rejected(keys):
    token = issue(keys)
    parts = token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    with pytest.raises(AuthenticationError):
        decode_token(".".join(parts), keys[1])


def test_symmetric_algorithm_rejected(keys):
    token = jwt.encode(
        {"sub": str(uuid4()), "exp": int(datetime.now(UTC).timestamp()) + 60},
        "untrusted-test-secret",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        decode_token(token, keys[1])


@pytest.mark.parametrize("expected", ["access", "refresh"])
def test_token_types_are_not_interchangeable(keys, expected):
    factory = create_refresh_token if expected == "access" else create_access_token
    token = factory(str(uuid4()), "user@example.com", keys[0])
    with pytest.raises(AuthenticationError):
        decode_token(token, keys[1], expected_type=expected)


def test_public_key_cannot_sign(keys):
    with pytest.raises((ValueError, TypeError)):
        issue((keys[1], keys[1]))


def test_unknown_kid_rejected(keys):
    token = issue(keys)
    token = jwt.encode(
        jwt.get_unverified_claims(token), keys[0], algorithm="RS256", headers={"kid": "unknown"}
    )
    with pytest.raises(AuthenticationError):
        decode_token(token, keys[1])
