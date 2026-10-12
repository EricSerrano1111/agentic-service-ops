"""The full-system deploy plan and definitions (ADR-099). Nothing here touches GCP.

`deploy/plan_full.py --dry-run` is the plan; the six definitions under `deploy/cloudrun/` are
rendered with placeholder values. The checks are the security properties the ADR rests on:
one public service, the database secrets only where the database is, the model key only where
a model is called, and the connection budget against `max_connections` = 60.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"deploy_full_{name}", DEPLOY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("render")
plan_full = _load("plan_full")
CFG = plan_full.Config(image_tag="abc123")
DEFINITIONS = ["gateway", "orchestrator", "reporting", "sentiment", "forecast", "qa"]
DB_SECRETS = {
    "db-role-reporting-password",
    "db-role-sentiment-password",
    "db-role-forecast-password",
    "db-role-qa-password",
}
#: Containers that make a model call, and so are the only ones that may hold the Gemini key.
MODEL_CALLERS = {
    "ops-orchestrator": {"orchestrator"},
    "ops-reporting": {"agent-reporting"},
    "ops-sentiment": {"agent-sentiment"},
    "ops-forecast": {"agent-forecast"},
    "ops-qa": {"agent-qa"},
}
#: The only containers that may hold a database password: the MCP sidecars and QA.
DB_HOLDERS = {"mcp-incidents", "mcp-feedback", "mcp-volume", "agent-qa"}


def rendered(name: str) -> dict:
    return render.render_file(DEPLOY / "cloudrun" / f"{name}.yaml", CFG.render_env())


def secrets_by_container() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for name in DEFINITIONS:
        doc = rendered(name)
        service = doc["name"].rsplit("/", 1)[1]
        for c in doc["template"]["containers"]:
            out[(service, c["name"])] = {
                e["valueSource"]["secretKeyRef"]["secret"]
                for e in c.get("env", [])
                if "valueSource" in e
            }
    return out


def dry_run() -> list[plan_full.Step]:
    return plan_full.build_plan(CFG)


# ------------------------------------------------------------------------------ the plan


def test_dry_run_prints_every_step_in_order_and_starts_no_process(monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise AssertionError("dry run started a process")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    assert plan_full.main(["--dry-run", "--image-tag", "abc123"]) == 0
    out = capsys.readouterr().out
    steps = dry_run()
    numbers = [int(m) for m in re.findall(r"^\[(\d+)\] ", out, flags=re.M)]
    assert numbers == list(range(1, len(steps) + 1))
    assert f"{len(steps)} steps" in out


def test_the_phases_run_accounts_then_secrets_then_access_then_roles_then_services():
    phases = [s.phase.split()[0] for s in dry_run()]
    assert phases == sorted(phases)
    assert phases[0] == "1" and phases[-1] == "6"


def test_services_deploy_in_dependency_order_and_each_is_bound_right_after():
    steps = dry_run()
    deploys = [s.service for s in steps if s.id.startswith("deploy-")]
    assert deploys == ["qa", "sentiment", "forecast", "reporting", "orchestrator", "gateway"]
    ids = [s.id for s in steps]
    for name in deploys:
        assert ids.index(f"invoker-{name}") == ids.index(f"deploy-{name}") + 1
    # secrets and accounts exist before any service is created
    first_deploy = ids.index("deploy-qa")
    assert all(
        ids.index(i) < first_deploy for i in ids if i.startswith(("sa-", "secret-", "access-"))
    )


def test_phases_and_skip_deploy_select_the_runbook_runs():
    first = plan_full.select(dry_run(), "1,2,3,4,5", False)
    assert first and not any(s.phase.startswith("6") for s in first)
    bindings = plan_full.select(dry_run(), "6", True)
    assert bindings and all(s.id.startswith("invoker-") for s in bindings)
    assert {s.binding[0] for s in bindings if s.binding} >= {"qa", "orchestrator", "gateway"}


def test_only_sentiment_is_blocked_and_it_says_why():
    blocked = [s for s in dry_run() if s.blocked]
    assert {s.id for s in blocked} == {"deploy-sentiment", "invoker-sentiment"}
    assert all("R-19" in s.blocked for s in blocked)


def test_a_real_run_skips_what_exists_and_blocked_steps_and_pipes_secrets(monkeypatch):
    calls: list[tuple[list[str], str | None]] = []

    class Done:
        def __init__(self, rc: int) -> None:
            self.returncode = rc

    def run(argv, input=None, **kwargs):
        calls.append((argv, input))
        # every describe (check) succeeds: the secrets and accounts "exist"
        return Done(0)

    lines: list[str] = []
    rc = plan_full.run_plan(dry_run(), CFG, run=run, generate=lambda: "TOKEN", out=lines.append)
    assert rc == 0
    assert any("exists, skipped: create gateway-session-key" in x for x in lines)
    assert any("SKIP (blocked" in x for x in lines)
    assert not any("sentiment.json" in " ".join(a) for a, _ in calls)

    calls.clear()

    def fresh(argv, input=None, **kwargs):
        calls.append((argv, input))
        return Done(1 if "describe" in argv else 0)  # nothing exists yet

    plan_full.run_plan(dry_run(), CFG, run=fresh, generate=lambda: "TOKEN", out=lambda _: None)
    created = [(a, i) for a, i in calls if "create" in a and "gateway-session-key" in a]
    assert created and created[0][1] == "TOKEN"
    invites = [(a, i) for a, i in calls if "create" in a and "gateway-invites" in a]
    assert invites[0][1] == '{"invites": []}'


def test_a_failed_step_stops_the_run():
    class Done:
        returncode = 1

    lines: list[str] = []
    rc = plan_full.run_plan(
        dry_run(), CFG, run=lambda *a, **k: Done(), generate=lambda: "T", out=lines.append
    )
    assert rc == 1 and any("FAILED" in x for x in lines)


# ------------------------------------------------------------------------ the bindings


def test_allusers_is_bound_on_the_gateway_and_on_no_other_service():
    public = [s for s in dry_run() if s.binding and s.binding[1] == "allUsers"]
    assert [s.binding[0] for s in public] == ["gateway"]
    for s in dry_run():
        text = " ".join(" ".join(c) for c in s.commands)
        if "allUsers" in text or "allAuthenticatedUsers" in text:
            assert s.id == "invoker-gateway"
    assert "allAuthenticatedUsers" not in " ".join(
        " ".join(c) for s in dry_run() for c in s.commands
    )


@pytest.mark.parametrize("name", DEFINITIONS)
def test_no_definition_switches_the_invoker_check_off(name):
    assert rendered(name)["invokerIamDisabled"] is False


def test_each_invoker_is_the_one_account_that_calls_the_service():
    bound = {
        s.binding[0]: s.binding[1]
        for s in dry_run()
        if s.binding and s.id != "invoker-orchestrator-build"
    }
    assert bound == {
        "qa": "run-orchestrator",
        "sentiment": "run-orchestrator",
        "forecast": "run-orchestrator",
        "reporting": "run-orchestrator",
        "orchestrator": "run-gateway",
        "gateway": "allUsers",
    }


def test_the_orchestrator_is_not_public_and_the_gateway_may_call_only_it():
    steps = dry_run()
    gateway_roles = [s for s in steps if s.binding and s.binding[1] == "run-gateway"]
    assert [s.binding[0] for s in gateway_roles] == ["orchestrator"]


def test_cloudsql_client_goes_only_to_the_three_new_database_accounts():
    holders = {s.id.removeprefix("cloudsql-") for s in dry_run() if s.id.startswith("cloudsql-")}
    assert holders == {"run-sentiment", "run-forecast", "run-qa"}


def test_each_account_may_read_only_its_own_secrets_and_none_project_wide():
    expected = {
        ("db-role-qa-password", "run-qa"),
        ("gemini-api-key", "run-qa"),
        ("db-role-sentiment-password", "run-sentiment"),
        ("gemini-api-key", "run-sentiment"),
        ("db-role-forecast-password", "run-forecast"),
        ("gemini-api-key", "run-forecast"),
        ("db-role-reporting-password", "run-reporting"),
        ("gemini-api-key", "run-reporting"),
        ("gemini-api-key", "run-orchestrator"),
        ("gateway-session-key", "run-gateway"),
        ("gateway-invites", "run-gateway"),
    }
    assert {s.secret_access for s in dry_run() if s.secret_access} == expected
    for s in dry_run():
        text = " ".join(" ".join(c) for c in s.commands)
        assert "roles/secretmanager.admin" not in text
        if "secretmanager.secretAccessor" in text:
            assert s.commands[0][1:3] == ("secrets", "add-iam-policy-binding")


# --------------------------------------------------------------------- the definitions


@pytest.mark.parametrize("name", DEFINITIONS)
def test_every_definition_renders_and_runs_as_its_own_account(name):
    doc = rendered(name)
    assert "${" not in str(doc)
    sa = doc["template"]["serviceAccount"]
    assert "compute@developer" not in sa and sa.startswith("run-")
    assert doc["template"]["scaling"]["minInstanceCount"] == 0
    assert doc["template"]["scaling"]["maxInstanceCount"] <= 3


def test_the_six_services_use_six_different_accounts():
    accounts = {rendered(n)["template"]["serviceAccount"] for n in DEFINITIONS}
    assert len(accounts) == 6


def test_no_database_secret_outside_the_mcp_containers_and_qa():
    for (service, container), names in secrets_by_container().items():
        if names & DB_SECRETS:
            assert container in DB_HOLDERS, f"{service}/{container} holds a database secret"
    holders = {c for (_, c), names in secrets_by_container().items() if names & DB_SECRETS}
    assert holders == DB_HOLDERS


def test_each_database_container_holds_only_its_own_roles_password():
    own = {
        "mcp-incidents": "db-role-reporting-password",
        "mcp-feedback": "db-role-sentiment-password",
        "mcp-volume": "db-role-forecast-password",
        "agent-qa": "db-role-qa-password",
    }
    for (_, container), names in secrets_by_container().items():
        if container in own:
            assert names & DB_SECRETS == {own[container]}


def test_the_gemini_key_is_only_in_containers_that_call_a_model():
    holders = {
        (service, container)
        for (service, container), names in secrets_by_container().items()
        if "gemini-api-key" in names
    }
    assert holders == {(s, c) for s, cs in MODEL_CALLERS.items() for c in cs}


def test_the_gateway_holds_no_database_credential_no_model_key_and_no_socket():
    doc = rendered("gateway")
    assert "volumes" not in doc["template"]
    (container,) = doc["template"]["containers"]
    assert "volumeMounts" not in container
    names = {e["name"] for e in container["env"]}
    assert not any(n.startswith(("DB_ROLE_", "POSTGRES_", "GOOGLE_", "GEMINI_")) for n in names)
    secret_names = secrets_by_container()[("ops-gateway", "gateway")]
    assert secret_names == {"gateway-session-key"}  # gateway-invites is read through the API
    env = {e["name"]: e.get("value") for e in container["env"]}
    assert env["GATEWAY_INVITES_SECRET"] == f"projects/{CFG.project_number}/secrets/gateway-invites"
    assert env["GATEWAY_AUTH"] == "google_id_token"


def test_the_cloud_sql_socket_is_in_exactly_the_database_containers():
    mounted = set()
    for name in DEFINITIONS:
        doc = rendered(name)
        for c in doc["template"]["containers"]:
            if any(m["name"] == "cloudsql" for m in c.get("volumeMounts", [])):
                mounted.add(c["name"])
    assert mounted == DB_HOLDERS


def test_qa_has_no_volume_other_than_the_socket_and_no_sidecar():
    doc = rendered("qa")
    assert [v["name"] for v in doc["template"]["volumes"]] == ["cloudsql"]
    assert [c["name"] for c in doc["template"]["containers"]] == ["agent-qa"]


def test_the_orchestrator_names_every_callee_by_its_deterministic_url():
    env = {
        e["name"]: e.get("value")
        for e in rendered("orchestrator")["template"]["containers"][0]["env"]
    }
    base = f"https://ops-{{}}-{CFG.project_number}.{CFG.region}.run.app"
    assert env["AGENT_REPORTING_URL"] == base.format("reporting")
    assert env["AGENT_SENTIMENT_URL"] == base.format("sentiment")
    assert env["AGENT_FORECAST_URL"] == base.format("forecast")
    assert env["AGENT_QA_URL"] == base.format("qa")
    assert env["A2A_AUTH"] == "google_id_token"


def test_the_gateway_and_the_orchestrator_agree_on_the_orchestrator_url():
    gateway = {
        e["name"]: e.get("value") for e in rendered("gateway")["template"]["containers"][0]["env"]
    }
    assert gateway["GATEWAY_ORCHESTRATOR_URL"] == (
        f"https://ops-orchestrator-{CFG.project_number}.{CFG.region}.run.app"
    )


def test_every_service_has_the_cost_split_label():
    for name in DEFINITIONS:
        assert rendered(name)["labels"]["component"] == "deploy"


# ------------------------------------------------------------------ connection budget

POOL = 4  # SQLAlchemy pool_size 2 + max_overflow 2 in every database container
DB_SERVICES = {"ops-reporting", "ops-sentiment", "ops-forecast", "ops-qa"}
MAX_CONNECTIONS = 60
RESERVED = 10  # superuser_reserved_connections (3) and Cloud SQL's own sessions (ADR-099)
OWNER_SESSIONS = 4  # backfill and migration through the Auth Proxy


@pytest.mark.parametrize(
    "path",
    [
        "services/mcp_incidents/src/mcp_incidents/queries.py",
        "services/mcp_feedback/src/mcp_feedback/store.py",
        "services/mcp_volume/src/mcp_volume/store.py",
        "services/agent_qa/src/agent_qa/db.py",
    ],
)
def test_the_pool_size_the_arithmetic_assumes_is_what_the_code_sets(path):
    text = (REPO / path).read_text(encoding="utf-8")
    assert "pool_size=2" in text and "max_overflow=2" in text


def test_the_connection_budget_fits_max_connections():
    total = 0
    for name in DEFINITIONS:
        doc = rendered(name)
        service = doc["name"].rsplit("/", 1)[1]
        if service in DB_SERVICES:
            total += doc["template"]["scaling"]["maxInstanceCount"] * POOL
    assert total == 32
    assert total + RESERVED + OWNER_SESSIONS <= MAX_CONNECTIONS
    # the gateway and the orchestrator hold no connection: no socket, no database variable
    for name in ("gateway", "orchestrator"):
        assert "volumes" not in rendered(name)["template"]
