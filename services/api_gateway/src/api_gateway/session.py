"""The session cookie (ADR-097): an HMAC-SHA256-signed payload of the invite id, issued-at and
expiry. The signature is checked in constant time; the invite's continued existence is checked
by the caller on every request, so revoking an invite ends its sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass

COOKIE_NAME = "__Host-session"
#: A session lasts at most this long, and never past its invite's expiry.
MAX_SESSION_S = 12 * 3600
MIN_KEY_CHARS = 32


@dataclass(frozen=True)
class SessionClaims:
    invite_id: str
    issued_at: float
    expires_at: float


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(key: str, body: str) -> str:
    return _b64(hmac.new(key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())


def sign(claims: SessionClaims, key: str) -> str:
    payload = json.dumps(
        {"iid": claims.invite_id, "iat": claims.issued_at, "exp": claims.expires_at},
        separators=(",", ":"),
    )
    body = _b64(payload.encode("utf-8"))
    return f"{body}.{_mac(key, body)}"


def verify(value: str, key: str, now: float) -> SessionClaims | None:
    """The claims of a validly signed, unexpired cookie value, or None."""
    try:
        body, mac = value.split(".")
        if not hmac.compare_digest(mac, _mac(key, body)):
            return None
        raw = json.loads(_unb64(body))
        claims = SessionClaims(str(raw["iid"]), float(raw["iat"]), float(raw["exp"]))
    except (ValueError, KeyError, TypeError, UnicodeError):
        return None
    return claims if now < claims.expires_at else None
