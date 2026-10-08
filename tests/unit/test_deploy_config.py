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
    assert secret_names(cs["agent-reporting"]) == {"GOOGLE_AI_API_KEY"}
    assert not any(n.startswith("DB_") for n in env_names(cs["agent-reporting"]))
    orch = containers(rendered("orchestrator"))["orchestrator"]
    assert secret_names(orch) == {"GOOGLE_AI_API_KEY"}
    assert not any(n.startswith(("DB_", "POSTGRES", "CLOUD_SQL")) for n in env_names(orch))


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
    assert steps["verify"]["waitFor"] == ["deploy-orchestrator"]
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
