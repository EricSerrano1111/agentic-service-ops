"""The deploy drafts under deploy/: structure, rendering and the post-deploy checks.

Nothing here touches GCP. The service definitions are checked for the properties ADR-079 and
ADR-081 depend on; verify.py's checks are pure functions of gcloud's JSON.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"

ENV = {
    "PROJECT_ID": "proj-x",
    "PROJECT_NUMBER": "123456789",
    "REGION": "us-central1",
    "AR_REPO": "ops",
    "IMAGE_TAG": "abc123",
    "ORCHESTRATOR_SA": "orch@proj-x.iam.gserviceaccount.com",
    "REPORTING_SA": "rep@proj-x.iam.gserviceaccount.com",
    "CLOUD_SQL_INSTANCE": "proj-x:us-central1:ops-db",
    "POSTGRES_DB": "service_ops",
    "GEMINI_MODEL_ORCHESTRATOR": "m1",
    "GEMINI_MODEL_SPECIALIST": "m2",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"deploy_{name}", DEPLOY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("render")
verify = _load("verify")


def rendered(name: str) -> dict:
    return render.render_file(DEPLOY / "cloudrun" / f"{name}.yaml", ENV)


def containers(doc: dict) -> dict[str, dict]:
    return {c["name"]: c for c in doc["template"]["containers"]}


def env_names(container: dict) -> set[str]:
    return {e["name"] for e in container.get("env", [])}


def secret_names(container: dict) -> set[str]:
    return {e["name"] for e in container.get("env", []) if "valueSource" in e}


# ---------------------------------------------------------------------------- rendering


def test_every_placeholder_resolves_and_none_remain():
    for name in ("reporting", "orchestrator"):
        assert "${" not in str(rendered(name))


def test_render_fails_on_an_unset_placeholder():
    env = {k: v for k, v in ENV.items() if k != "IMAGE_TAG"}
    with pytest.raises(render.UnresolvedPlaceholder, match="IMAGE_TAG"):
        render.render_file(DEPLOY / "cloudrun" / "reporting.yaml", env)


def test_render_fails_on_an_empty_value_and_on_a_placeholder_inside_a_value():
    with pytest.raises(render.UnresolvedPlaceholder):
        render.render_value("${A}", {"A": ""})
    with pytest.raises(render.UnresolvedPlaceholder):
        render.render_value("${A}", {"A": "${B}"})


def test_render_cli_exit_codes(tmp_path, monkeypatch):
    out = tmp_path / "r.json"
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert render.main(["render.py", str(DEPLOY / "cloudrun" / "reporting.yaml"), str(out)]) == 0
    monkeypatch.delenv("REGION")
    assert render.main(["render.py", str(DEPLOY / "cloudrun" / "reporting.yaml"), str(out)]) == 1


# ---------------------------------------------------------------------------- reporting


def test_cloud_sql_is_mounted_into_the_mcp_sidecar_only():
    doc = rendered("reporting")
    cs = containers(doc)
    assert [v["name"] for v in doc["template"]["volumes"]] == ["cloudsql"]
    assert doc["template"]["volumes"][0]["cloudSqlInstance"]["instances"] == [
        ENV["CLOUD_SQL_INSTANCE"]
    ]
    assert cs["mcp-incidents"]["volumeMounts"] == [{"name": "cloudsql", "mountPath": "/cloudsql"}]
    assert "volumeMounts" not in cs["agent-reporting"]
    assert "CLOUD_SQL_INSTANCE" not in env_names(cs["agent-reporting"])


def test_secrets_go_only_to_the_containers_that_need_them():
    cs = containers(rendered("reporting"))
    assert secret_names(cs["mcp-incidents"]) == {"DB_ROLE_REPORTING_PASSWORD"}
    assert secret_names(cs["agent-reporting"]) == {"GOOGLE_AI_API_KEY", "GOOGLE_AI_API_KEY_PAID"}
    assert not any(n.startswith("DB_") for n in env_names(cs["agent-reporting"]))
    orch = containers(rendered("orchestrator"))["orchestrator"]
    assert secret_names(orch) == {"GOOGLE_AI_API_KEY", "GOOGLE_AI_API_KEY_PAID"}
    assert not any(n.startswith(("DB_", "POSTGRES", "CLOUD_SQL")) for n in env_names(orch))


#: The five containers that call the model (ADR-104), by service file.
MODEL_CALLING = {
    "orchestrator": "orchestrator",
    "reporting": "agent-reporting",
    "sentiment": "agent-sentiment",
    "forecast": "agent-forecast",
    "qa": "agent-qa",
}


def _raw_containers(service: str) -> dict[str, dict]:
    """The checked-in definition, unrendered: `${...}` placeholders are plain strings."""
    doc = yaml.safe_load((DEPLOY / "cloudrun" / f"{service}.yaml").read_text("utf-8"))
    return {c["name"]: c for c in doc["template"]["containers"]}


def _env_values(container: dict) -> dict[str, object]:
    return {
        e["name"]: (e.get("value") if "value" in e else e["valueSource"]["secretKeyRef"])
        for e in container.get("env", [])
    }


@pytest.mark.parametrize(("service", "name"), sorted(MODEL_CALLING.items()))
def test_the_five_model_calling_containers_are_in_paid_mode_as_deployed(service, name):
    """The repo definition equals the deployed configuration of 2026-10-13 (ADR-104).

    Otherwise the first deploy after the trigger is enabled would revert the five services to
    the free key. The free key stays referenced beside the paid one (a revert is one env change).
    """
    env = _env_values(_raw_containers(service)[name])
    assert env["LLM_MODE"] == "paid"
    assert env["LLM_MAX_REQUESTS"] == "1500"
    assert env["LLM_MAX_SPEND_USD"] == "1.00"
    assert env["GOOGLE_AI_API_KEY_PAID"] == {"secret": "gemini-api-key-paid", "version": "latest"}
    assert env["GOOGLE_AI_API_KEY"] == {"secret": "gemini-api-key", "version": "latest"}


def test_no_sidecar_and_not_the_gateway_is_in_paid_mode_or_holds_a_model_key():
    for service in ("reporting", "sentiment", "forecast", "qa", "orchestrator", "gateway"):
        for name, container in _raw_containers(service).items():
            if name == MODEL_CALLING.get(service):
                continue
            env = _env_values(container)
            assert env.get("LLM_MODE") != "paid", (service, name)
            assert not {"GOOGLE_AI_API_KEY", "GOOGLE_AI_API_KEY_PAID"} & set(env), (service, name)


def test_exactly_the_five_model_calling_containers_are_in_paid_mode():
    paid = {
        (service, name)
        for service in ("reporting", "sentiment", "forecast", "qa", "orchestrator", "gateway")
        for name, c in _raw_containers(service).items()
        if _env_values(c).get("LLM_MODE") == "paid"
    }
    assert paid == {(service, name) for service, name in MODEL_CALLING.items()}


def test_the_agent_waits_for_a_sidecar_whose_probe_is_its_readiness_endpoint():
    cs = containers(rendered("reporting"))
    assert cs["agent-reporting"]["dependsOn"] == ["mcp-incidents"]
    assert cs["mcp-incidents"]["startupProbe"]["httpGet"] == {"path": "/readyz", "port": 8101}
    assert cs["agent-reporting"]["startupProbe"]["httpGet"] == {"path": "/readyz", "port": 8080}
    # Only the ingress container exposes a port.
    assert "ports" in cs["agent-reporting"] and "ports" not in cs["mcp-incidents"]


def test_agent_reaches_the_sidecar_on_localhost_and_advertises_its_run_app_url():
    agent = containers(rendered("reporting"))["agent-reporting"]
    env = {e["name"]: e.get("value") for e in agent["env"]}
    assert env["MCP_INCIDENTS_URL"] == "http://localhost:8101/mcp"
    assert (
        env["AGENT_REPORTING_PUBLIC_URL"] == "https://ops-reporting-123456789.us-central1.run.app/"
    )


@pytest.mark.parametrize("name", ["reporting", "orchestrator"])
def test_service_level_settings(name):
    doc = rendered(name)
    template = doc["template"]
    assert (
        template["serviceAccount"]
        == ENV[f"{'ORCHESTRATOR' if name == 'orchestrator' else 'REPORTING'}_SA"]
    )
    assert "compute@developer" not in template["serviceAccount"]
    assert template["scaling"]["minInstanceCount"] == 0
    assert int(template["timeout"].rstrip("s")) >= 120
    assert doc["invokerIamDisabled"] is False


def test_orchestrator_signs_its_a2a_calls_and_points_at_the_deterministic_reporting_url():
    orch = containers(rendered("orchestrator"))["orchestrator"]
    env = {e["name"]: e.get("value") for e in orch["env"]}
    assert env["A2A_AUTH"] == "google_id_token"
    assert env["AGENT_REPORTING_URL"] == "https://ops-reporting-123456789.us-central1.run.app"


def test_no_public_invoker_and_no_real_identifiers_in_the_drafts():
    for path in (DEPLOY / "cloudrun").glob("*.yaml"):
        body = str(yaml.safe_load(path.read_text()))  # parsed: comments may name the principals
        assert "allUsers" not in body and "allAuthenticatedUsers" not in body
        assert "developer.gserviceaccount.com" not in body
    for path in DEPLOY.rglob("*"):
        if path.is_file() and path.suffix in {".yaml", ".md", ".py"}:
            assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", path.read_text()), path


# ---------------------------------------------------------------------------- cloud build


def test_cloud_build_runs_as_a_dedicated_account_and_renders_before_it_deploys():
    cb = yaml.safe_load((DEPLOY / "cloudbuild.yaml").read_text())
    assert cb["serviceAccount"].endswith("${_BUILD_SA}")
    assert cb["options"]["logging"] == "CLOUD_LOGGING_ONLY"
    steps = {s["id"]: s for s in cb["steps"]}
    assert "render" in steps["deploy-reporting"]["waitFor"]
    assert steps["deploy-orchestrator"]["waitFor"] == ["deploy-reporting"]
    assert steps["verify"]["waitFor"] == ["deploy-gateway"]  # the last of the six (ADR-099)
    assert set(steps["render"]["waitFor"]) == {"push-images"}
    for image in ("orchestrator", "agent-reporting", "mcp-incidents"):
        assert any(f"{image}:${{COMMIT_SHA}}" in " ".join(s.get("args", [])) for s in cb["steps"])
    # Every ${...} in the file is a Cloud Build substitution that exists.
    declared = set(cb["substitutions"]) | {"PROJECT_ID", "PROJECT_NUMBER", "COMMIT_SHA"}
    used = set(re.findall(r"(?<!\$)\$\{(\w+)\}", (DEPLOY / "cloudbuild.yaml").read_text()))
    assert used <= declared, used - declared


# ---------------------------------------------------------------------------- verify checks

SHA = "abc123"


def service(name="ops-reporting", sa="rep@p.iam.gserviceaccount.com", traffic=None, tag=SHA):
    return {
        "metadata": {"name": name},
        "status": {
            "latestReadyRevisionName": f"{name}-00002",
            "traffic": traffic or [{"revisionName": f"{name}-00002", "percent": 100}],
        },
        "spec": {
            "template": {
                "spec": {
                    "serviceAccountName": sa,
                    "containers": [{"image": f"r/x/a:{tag}"}, {"image": f"r/x/b:{tag}"}],
                }
            }
        },
    }


def test_serving_revision_passes_only_for_the_new_revision_with_all_traffic():
    assert verify.serving_revision(service(), SHA).ok
    split = [
        {"revisionName": "ops-reporting-00002", "percent": 50},
        {"revisionName": "old", "percent": 50},
    ]
    assert not verify.serving_revision(service(traffic=split), SHA).ok
    old = [{"revisionName": "ops-reporting-00001", "percent": 100}]
    assert not verify.serving_revision(service(traffic=old), SHA).ok
    assert not verify.serving_revision(service(tag="old"), SHA).ok


def test_refused_means_401_or_403():
    assert verify.refused("x", 401).ok and verify.refused("x", 403).ok
    assert not verify.refused("x", 200).ok and not verify.refused("x", None).ok


ORCH = "serviceAccount:orch@p.iam.gserviceaccount.com"


def test_invokers_requires_exactly_the_orchestrator_and_nothing_public():
    ok = {"bindings": [{"role": "roles/run.invoker", "members": [ORCH]}]}
    assert verify.invokers(ok, ORCH).ok
    for bad in (
        {"bindings": []},
        {"bindings": [{"role": "roles/run.invoker", "members": [ORCH, "user:a@b.c"]}]},
        {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]},
        {
            "bindings": [
                {"role": "roles/run.invoker", "members": [ORCH]},
                {"role": "roles/x", "members": ["allAuthenticatedUsers"]},
            ]
        },
    ):
        assert not verify.invokers(bad, ORCH).ok


def test_default_compute_account_fails():
    default = "123456789-compute@developer.gserviceaccount.com"
    assert not verify.not_default_compute(service(sa=default), "123456789", default).ok
    assert not verify.not_default_compute(
        service(sa=""), "123456789", "rep@p.iam.gserviceaccount.com"
    ).ok
    assert not verify.not_default_compute(
        service(sa="other@p.iam.gserviceaccount.com"), "1", "rep@p.iam.gserviceaccount.com"
    ).ok
    assert verify.not_default_compute(service(), "123456789", "rep@p.iam.gserviceaccount.com").ok


def test_authorized_networks_must_be_empty():
    assert verify.no_authorized_networks(
        {"settings": {"ipConfiguration": {"ipv4Enabled": True}}}
    ).ok
    assert verify.no_authorized_networks(
        {"settings": {"ipConfiguration": {"authorizedNetworks": []}}}
    ).ok
    open_net = {"settings": {"ipConfiguration": {"authorizedNetworks": [{"value": "0.0.0.0/0"}]}}}
    assert not verify.no_authorized_networks(open_net).ok


def test_answered_needs_an_answered_outcome_with_figures():
    assert verify.answered(200, {"outcome": "answered", "reporting": {"a": 1}}).ok
    assert not verify.answered(200, {"outcome": "declined"}).ok
    assert not verify.answered(502, {"error": "agent_unavailable"}).ok


def test_check_lines_say_pass_or_fail():
    assert verify.Check("n", True).line().startswith("PASS")
    assert verify.Check("n", False, "why").line() == "FAIL  n: why"


def test_the_first_run_can_skip_verify_and_later_runs_do_not():
    cb = yaml.safe_load((DEPLOY / "cloudbuild.yaml").read_text())
    assert cb["substitutions"]["_RUN_VERIFY"] == "true"  # verified unless explicitly skipped
    verify_step = next(s for s in cb["steps"] if s["id"] == "verify")
    script = " ".join(verify_step["args"])
    assert '"${_RUN_VERIFY}" = "true"' in script and "deploy/verify.py" in script


# ------------------------------------------------------------------ labels, accounts, secrets


@pytest.mark.parametrize("name", ["reporting", "orchestrator"])
def test_both_services_carry_the_cost_split_labels(name):
    assert rendered(name)["labels"] == {"app": "agentic-service-ops", "component": "deploy"}


def test_cloud_build_defaults_to_the_four_decided_service_accounts_and_the_repo():
    subs = yaml.safe_load((DEPLOY / "cloudbuild.yaml").read_text())["substitutions"]
    domain = "@a2a-agentic-service-ops-gcp.iam.gserviceaccount.com"
    assert subs["_BUILD_SA"] == "build-deploy" + domain
    assert subs["_ORCHESTRATOR_SA"] == "run-orchestrator" + domain
    assert subs["_REPORTING_SA"] == "run-reporting" + domain
    assert subs["_PROBE_SA"] == "probe-noauth" + domain
    assert subs["_AR_REPO"] == "agentic-service-ops"
    # None of the four is the default compute account.
    assert not any("compute@developer" in v for v in subs.values())


def test_readme_names_every_secret_the_deploy_creates():
    readme = (DEPLOY / "README.md").read_text()
    for secret in (
        "gemini-api-key",
        "db-admin-password",
        "db-role-reporting-password",
        "db-role-sentiment-password",
        "db-role-forecast-password",
        "db-role-qa-password",
        "db-role-generator-password",
        "db-role-eval-password",
        "db-role-train-password",
    ):
        assert f"`{secret}`" in readme, secret
    assert "newly generated" in readme and "never copied from" in readme


def test_create_body_has_no_name_but_the_update_body_keeps_it():
    ds = _load("deploy_service")
    doc = rendered("reporting")
    assert "name" in doc and "name" not in ds.create_body(doc)
    assert ds.create_body(doc) == {k: v for k, v in doc.items() if k != "name"}


def test_ingress_probes_are_ask_and_root_on_the_orchestrator_and_root_on_reporting():
    assert verify.INGRESS_PROBES == (
        ("orchestrator", "POST", "/ask"),
        ("orchestrator", "GET", "/"),
        ("reporting", "GET", "/"),
    )
    assert all(path != "/healthz" for _, _, path in verify.INGRESS_PROBES)


def test_unauthenticated_probes_pass_on_401_and_403():
    checks = verify.unauthenticated_refused(
        {
            ("orchestrator", "POST", "/ask"): 403,
            ("orchestrator", "GET", "/"): 401,
            ("reporting", "GET", "/"): 403,
        }
    )
    assert len(checks) == 3 and all(c.ok for c in checks)


@pytest.mark.parametrize("bad", [404, 200, 204, 302, 500, 502, 503, None])
@pytest.mark.parametrize("which", verify.INGRESS_PROBES)
def test_any_other_status_fails_that_probe_only(which, bad):
    checks = verify.unauthenticated_refused({p: 403 for p in verify.INGRESS_PROBES} | {which: bad})
    failed = [c for c in checks if not c.ok]
    assert len(failed) == 1 and which[0] in failed[0].name and which[2] in failed[0].name


def test_a_missing_probe_result_fails():
    checks = verify.unauthenticated_refused({})
    assert len(checks) == 3 and not any(c.ok for c in checks)


ORCH_URL = "https://ops-orchestrator-x.a.run.app"


def test_pipeline_caller_is_minted_by_impersonating_caller_sa():
    sa = "b@p.iam.gserviceaccount.com"
    args = verify.caller_token_args({"CALLER_SA": sa}, ORCH_URL, sa)
    assert args == [
        "--impersonate-service-account=b@p.iam.gserviceaccount.com",
        f"--audiences={ORCH_URL}",
    ]


def test_owner_caller_uses_their_own_identity_when_caller_sa_is_unset():
    assert verify.caller_token_args({}, ORCH_URL, "owner@gmail.com") == []
    # A service-account login with no impersonation target still needs an audience.
    assert verify.caller_token_args({}, ORCH_URL, "x@p.iam.gserviceaccount.com") == [
        f"--audiences={ORCH_URL}"
    ]
    assert verify.caller_token_args({"CALLER_SA": ""}, ORCH_URL, "owner@gmail.com") == []


def test_a_failed_mint_is_a_fail_line_naming_the_reason():
    import subprocess

    exc = subprocess.CalledProcessError(1, ["gcloud"], stderr="ERROR: no token\nmore detail\n")
    check = verify.mint_failure(exc)
    assert not check.ok and "end to end" in check.name
    assert check.detail.endswith("ERROR: no token") and "more detail" not in check.detail
    assert verify.mint_failure(subprocess.CalledProcessError(1, ["gcloud"])).detail.endswith(
        "gcloud failed"
    )


def test_cloud_build_passes_the_build_account_as_the_caller():
    cb = yaml.safe_load((DEPLOY / "cloudbuild.yaml").read_text())
    verify_step = next(s for s in cb["steps"] if s["id"] == "verify")
    assert "CALLER_SA=${_BUILD_SA}" in verify_step["env"]


def _run_deploy_service(monkeypatch, tmp_path, existing: bool):
    """Drive deploy_service.main with a fake API; return the (method, url, body) calls."""
    import json

    ds = _load("deploy_service")
    path = tmp_path / "svc.json"
    path.write_text(json.dumps(rendered("reporting")))
    calls = []

    def fake_call(method, url, token, body=None):
        calls.append((method, url, body))
        if method == "GET" and "/operations/" not in url:
            return (200, {}) if existing else (404, {})
        return 200, {"name": "operations/x", "done": True}

    monkeypatch.setattr(ds, "access_token", lambda: "t")
    monkeypatch.setattr(ds, "call", fake_call)
    assert ds.main(["deploy_service.py", str(path)]) == 0
    return calls


def test_a_new_service_is_created_with_the_id_in_the_url_and_no_name_in_the_body(
    monkeypatch, tmp_path
):
    _, (method, url, body) = _run_deploy_service(monkeypatch, tmp_path, existing=False)
    assert method == "POST" and url.endswith("/services?serviceId=ops-reporting")
    assert "name" not in body


def test_an_existing_service_is_patched_with_its_name_in_the_body(monkeypatch, tmp_path):
    _, (method, url, body) = _run_deploy_service(monkeypatch, tmp_path, existing=True)
    assert method == "PATCH" and url.endswith("/services/ops-reporting")
    assert body["name"].endswith("/services/ops-reporting")


# ------------------------------------------------- verify.py: all six services (ADR-108, section 8)

PROJECT_DOMAIN = "proj-x.iam.gserviceaccount.com"


def _policy(*members, role="roles/run.invoker"):
    return {"bindings": [{"role": role, "members": list(members)}]}


def test_invokers_exactly_passes_for_the_expected_set_only():
    sa = f"serviceAccount:run-orchestrator@{PROJECT_DOMAIN}"
    assert verify.invokers_exactly("ops-qa", _policy(sa), {sa}).ok
    other = f"serviceAccount:run-gateway@{PROJECT_DOMAIN}"
    assert not verify.invokers_exactly("ops-qa", _policy(sa, other), {sa}).ok  # one too many
    assert not verify.invokers_exactly("ops-qa", _policy(other), {sa}).ok  # the wrong one
    assert not verify.invokers_exactly("ops-qa", {"bindings": []}, {sa}).ok  # none
    assert not verify.invokers_exactly("ops-qa", _policy(sa, "allUsers"), {sa}).ok  # public


def test_only_the_gateway_may_be_public():
    assert verify.invokers_exactly("ops-gateway", _policy("allUsers"), {"allUsers"}).ok
    assert not verify.invokers_exactly(
        "ops-gateway", _policy("allUsers", "allAuthenticatedUsers"), {"allUsers"}
    ).ok
    gateway_sa = f"serviceAccount:run-gateway@{PROJECT_DOMAIN}"
    assert not verify.invokers_exactly(
        "ops-orchestrator", _policy(gateway_sa, "allUsers"), {gateway_sa}
    ).ok


def _with_env(name="ops-qa", **containers):
    return {
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": cname,
                            "env": [{"name": "LLM_MODE", "value": mode}] if mode else [],
                        }
                        for cname, mode in containers.items()
                    ]
                }
            }
        },
    }


def test_paid_mode_is_required_on_the_model_container_and_forbidden_elsewhere():
    ok = _with_env("ops-reporting", **{"agent-reporting": "paid", "mcp-incidents": None})
    assert verify.paid_mode(ok, "agent-reporting").ok
    free = _with_env("ops-reporting", **{"agent-reporting": "free", "mcp-incidents": None})
    assert not verify.paid_mode(free, "agent-reporting").ok  # the 2026-10-13 drift
    sidecar = _with_env("ops-reporting", **{"agent-reporting": "paid", "mcp-incidents": "paid"})
    assert not verify.paid_mode(sidecar, "agent-reporting").ok
    gateway = _with_env("ops-gateway", gateway=None)
    assert verify.paid_mode(gateway, None).ok
    assert not verify.paid_mode(_with_env("ops-gateway", gateway="paid"), None).ok


def test_the_serving_check_reads_the_tag_at_the_service_template_not_the_revision_digest():
    svc = service()
    # A revision-level status listing digests must not decide the check (runbook 5e).
    svc["status"]["traffic"][0]["tag"] = "sha256:deadbeef"
    svc["status"]["latestCreatedRevisionName"] = "ops-reporting-00002"
    assert verify.serving_revision(svc, SHA).ok
    assert not verify.serving_revision(service(tag="9607fa72"), SHA).ok


def test_the_six_services_table_agrees_with_the_deploy_plan_and_the_definitions():
    plan = _load("plan_full")
    assert set(verify.SIX) == set(plan.SERVICES)
    for name, (account, allowed) in verify.SIX.items():
        assert account == plan.SERVICES[name]["sa"]
        expected = {plan.INVOKER[name]} | ({"build-deploy"} if name == "orchestrator" else set())
        assert allowed == expected, name
    # Exactly the five model-calling containers, as the definitions have them.
    assert set(verify.MODEL_CALLING) == {s for s in plan.SERVICES if s != "gateway"}
    assert dict(verify.MODEL_CALLING) == {
        service: container for service, container in MODEL_CALLING.items()
    }


ALL_SERVICES = ("gateway", "orchestrator", "reporting", "sentiment", "forecast", "qa")
#: container -> its own port: the nine containers of the six services
LIVENESS_PORTS = {
    "gateway": 8080,
    "orchestrator": 8080,
    "agent-reporting": 8080,
    "mcp-incidents": 8101,
    "agent-sentiment": 8080,
    "mcp-feedback": 8102,
    "agent-forecast": 8080,
    "mcp-volume": 8103,
    "agent-qa": 8080,
}


LATEST_100 = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]


@pytest.mark.parametrize("service", ALL_SERVICES)
def test_every_definition_sends_all_traffic_to_the_latest_ready_revision(service):
    """L-105: a PATCH carrying this block resets a manual `update-traffic` pin."""
    doc = yaml.safe_load((DEPLOY / "cloudrun" / f"{service}.yaml").read_text("utf-8"))
    assert doc["traffic"] == LATEST_100


def test_the_deploy_scripts_pass_the_traffic_block_through_unchanged():
    ds = _load("deploy_service")
    for service in ALL_SERVICES:
        raw = yaml.safe_load((DEPLOY / "cloudrun" / f"{service}.yaml").read_text("utf-8"))
        assert render.render_value(raw["traffic"], ENV) == LATEST_100, service
    doc = rendered("reporting")
    assert doc["traffic"] == LATEST_100
    assert ds.create_body(doc)["traffic"] == LATEST_100  # an update sends `doc` as it is


def test_every_container_has_a_liveness_probe_on_healthz_at_its_own_port():
    """F2: /healthz checks no database, so a stopped database never causes a restart loop."""
    seen = {}
    for service in ALL_SERVICES:
        for name, c in _raw_containers(service).items():
            seen[name] = c["livenessProbe"]
    assert {n: p["httpGet"]["port"] for n, p in seen.items()} == LIVENESS_PORTS
    for name, probe in seen.items():
        assert probe["httpGet"]["path"] == "/healthz", name
        assert (probe["periodSeconds"], probe["timeoutSeconds"], probe["failureThreshold"]) == (
            30,
            5,
            3,
        ), name


def test_qas_startup_probe_is_its_readiness_endpoint():
    """F1: QA starts only when the database answers as app_qa."""
    qa = _raw_containers("qa")["agent-qa"]
    assert qa["startupProbe"]["httpGet"] == {"path": "/readyz", "port": 8080}
    assert qa["startupProbe"]["failureThreshold"] * qa["startupProbe"]["periodSeconds"] >= 60


def test_the_deploy_scripts_pass_probes_through_unchanged():
    ds = _load("deploy_service")
    doc = rendered("reporting")
    body = ds.create_body(doc)  # an update sends `doc` as it is
    for source, sent in zip(
        doc["template"]["containers"], body["template"]["containers"], strict=True
    ):
        assert source["livenessProbe"]["httpGet"]["path"] == "/healthz"
        assert sent["livenessProbe"] == source["livenessProbe"]
        assert sent["startupProbe"] == source["startupProbe"]
    for service in ALL_SERVICES:  # render.py leaves every container's probes as written
        for name, c in _raw_containers(service).items():
            probes = {k: c[k] for k in ("startupProbe", "livenessProbe")}
            assert render.render_value(probes, ENV) == probes, (service, name)
