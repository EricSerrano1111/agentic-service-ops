"""`scripts/invites.py --secret`: the same commands against a Secret Manager document (ADR-097).

The secret's reader and writer are injected, so nothing here touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SECRET = "projects/123/secrets/gateway-invites"


@pytest.fixture(scope="module")
def invites_script():
    spec = importlib.util.spec_from_file_location("invites_script", REPO / "scripts" / "invites.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["invites_script"] = module
    spec.loader.exec_module(module)
    return module


class Fake:
    def __init__(self, text: str = '{"invites": []}') -> None:
        self.text, self.reads, self.writes = text, [], []

    def read(self, secret: str) -> str:
        self.reads.append(secret)
        return self.text

    def write(self, secret: str, text: str) -> None:
        self.writes.append((secret, text))
        self.text = text


def run(script, fake, *args):
    return script.main(["--secret", SECRET, *args], store_io=(fake.read, fake.write))


def test_create_adds_a_new_version_holding_only_the_hash(invites_script, capsys):
    fake = Fake()
    assert run(invites_script, fake, "create", "--label", "owner", "--days", "14") == 0
    out = capsys.readouterr().out
    token = out.split("#invite=")[1].split()[0]
    assert len(fake.writes) == 1 and fake.writes[0][0] == SECRET
    doc = json.loads(fake.writes[0][1])
    (record,) = doc["invites"]
    assert record["label"] == "owner" and token not in fake.writes[0][1]
    assert set(record) >= {"id", "token_sha256", "expires_at"}


def test_revoke_adds_a_version_without_the_invite_and_list_writes_nothing(invites_script, capsys):
    fake = Fake()
    run(invites_script, fake, "create", "--label", "a", "--days", "1")
    run(invites_script, fake, "create", "--label", "b", "--days", "1")
    invite_id = json.loads(fake.text)["invites"][0]["id"]
    writes = len(fake.writes)
    assert run(invites_script, fake, "list") == 0
    assert len(fake.writes) == writes
    assert "token_sha256" not in capsys.readouterr().out
    assert run(invites_script, fake, "revoke", "--id", invite_id) == 0
    assert [i["label"] for i in json.loads(fake.text)["invites"]] == ["b"]
    assert len(fake.writes) == writes + 1


def test_revoking_an_unknown_id_writes_nothing(invites_script):
    fake = Fake()
    assert run(invites_script, fake, "revoke", "--id", "nope") == 1
    assert fake.writes == []


def test_secret_and_file_together_are_refused(invites_script, tmp_path):
    fake = Fake()
    rc = invites_script.main(
        ["--secret", SECRET, "--file", str(tmp_path / "x.json"), "list"],
        store_io=(fake.read, fake.write),
    )
    assert rc == 2 and fake.reads == []
