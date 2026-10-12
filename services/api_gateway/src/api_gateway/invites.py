"""The invite store (ADR-097).

An invite is a record of an id, a label, the SHA-256 of a 32-byte random token, and its dates.
Only the hash is kept: a plain hash is right for a high-entropy token (it cannot be guessed or
brute-forced from its hash); slow password hashes are for low-entropy secrets. Revoking an
invite deletes its record.

The store is a JSON document behind a one-method interface, `invites()`. Locally it is a file
(read on every call, so a revoke is immediate); on Cloud Run it is a Secret Manager secret read
as `latest` and cached for at most `CACHE_TTL_S`, so a revoke takes effect within that time
with no redeploy. The gateway holds no database credential and `ops-db` is stopped when idle,
so sign-in does not depend on it.

Neither a token nor a hash is ever logged.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: The most a Secret Manager read is cached. Revocation takes effect within this.
CACHE_TTL_S = 60.0
#: 32 random bytes, URL-safe base64 without padding, is 43 characters.
TOKEN_LENGTH = 43


@dataclass(frozen=True)
class Invite:
    id: str
    label: str
    token_sha256: str
    created_at: dt.datetime
    expires_at: dt.datetime

    def expired(self, now: dt.datetime) -> bool:
        return now >= self.expires_at

    def public(self) -> dict[str, str]:
        """What `list` shows: never the hash."""
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    def to_json(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "token_sha256": self.token_sha256,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_json(cls, raw: dict) -> Invite:
        return cls(
            id=str(raw["id"]),
            label=str(raw["label"]),
            token_sha256=str(raw["token_sha256"]),
            created_at=dt.datetime.fromisoformat(raw["created_at"]),
            expires_at=dt.datetime.fromisoformat(raw["expires_at"]),
        )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_invite(label: str, days: float, now: dt.datetime) -> tuple[Invite, str]:
    """A new invite and its token. The token exists only in this return value."""
    token = new_token()
    invite = Invite(
        id=uuid.uuid4().hex[:12],
        label=label,
        token_sha256=hash_token(token),
        created_at=now,
        expires_at=now + dt.timedelta(days=days),
    )
    return invite, token


def parse_document(text: str) -> list[Invite]:
    """The invites in a store document. A malformed record is skipped (it can never match),
    so one bad entry does not lock everyone out."""
    try:
        raw = json.loads(text) if text.strip() else {}
    except ValueError:
        return []
    records = raw.get("invites", []) if isinstance(raw, dict) else []
    out = []
    for record in records:
        try:
            out.append(Invite.from_json(record))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def dump_document(invites: list[Invite]) -> str:
    return json.dumps({"invites": [i.to_json() for i in invites]}, indent=2) + "\n"


def find_by_token(invites: list[Invite], token: str, now: dt.datetime) -> Invite | None:
    """The unexpired invite whose hash matches, compared in constant time against every
    record (no early exit), or None. A malformed token is just a non-match."""
    if not isinstance(token, str) or not (1 <= len(token) <= 256):
        return None
    digest = hash_token(token)
    found: Invite | None = None
    for invite in invites:
        if hmac.compare_digest(invite.token_sha256, digest) and not invite.expired(now):
            found = invite
    return found


def find_by_id(invites: list[Invite], invite_id: str, now: dt.datetime) -> Invite | None:
    for invite in invites:
        if invite.id == invite_id and not invite.expired(now):
            return invite
    return None


class InviteStore(Protocol):
    def invites(self) -> list[Invite]: ...


class FileInviteStore:
    """A JSON file. Read on every call; written atomically by the admin tool."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def invites(self) -> list[Invite]:
        try:
            return parse_document(self.path.read_text(encoding="utf-8"))
        except OSError:
            return []

    def save(self, invites: list[Invite]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".invites-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(dump_document(invites))
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class SecretManagerInviteStore:
    """The document in a Secret Manager secret, `latest` version, cached for `ttl_s`.

    `fetch` returns the secret's text; it is injected so the offline suite tests this against a
    fake. A failed read keeps the last good copy for one more TTL (the gateway stays up through
    a blip) and returns no invites when there never was one (it fails closed).
    """

    def __init__(
        self,
        fetch: Callable[[], str],
        *,
        ttl_s: float = CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl = min(ttl_s, CACHE_TTL_S)
        self._clock = clock
        self._cached: list[Invite] = []
        self._at: float | None = None

    def invites(self) -> list[Invite]:
        now = self._clock()
        if self._at is not None and now - self._at < self._ttl:
            return self._cached
        # A failed read keeps the last good copy; the secret and the error text are never logged.
        with contextlib.suppress(Exception):
            self._cached = parse_document(self._fetch())
        self._at = now
        return self._cached


def secret_manager_fetch(secret: str) -> Callable[[], str]:
    """A reader for `projects/<p>/secrets/<name>` over the Secret Manager REST API, as the
    service account. `google-auth` is imported on first use, so local runs never load it."""

    def fetch() -> str:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(creds)
        resp = session.get(
            f"https://secretmanager.googleapis.com/v1/{secret}/versions/latest:access", timeout=5
        )
        resp.raise_for_status()
        return base64.b64decode(resp.json()["payload"]["data"]).decode("utf-8")

    return fetch
