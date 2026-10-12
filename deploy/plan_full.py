"""The deploy plan for the full system, as ordered steps (ADR-099; run in Prompt V).

    python deploy/plan_full.py --dry-run --image-tag <sha>      # print every step; no API call
    python deploy/plan_full.py --phases 1,2,3,4,5               # accounts, secrets, access, roles
    python deploy/plan_full.py --phases 6 --skip-deploy         # invoker bindings only
    python deploy/plan_full.py --image-tag <sha>                # run everything, checking first

Each step is one `gcloud` command (or a render + deploy of a service definition), with an
optional read-only `check`: if the check succeeds the thing exists and the step is skipped, so
a rerun is safe. `--dry-run` only prints: it makes no API call and starts no process.

Order: service accounts, secrets, secret access, project roles, build-account bindings, then
the services in dependency order (QA, sentiment, forecast, reporting, orchestrator, gateway),
each followed by its invoker binding. `ops-sentiment` deploys with the others (ADR-100): its
image is the weight-free `stored` target. A service entry may still carry `"blocked": <reason>`,
which prints its steps as BLOCKED and skips them in a real run; none does now.
Nothing here deploys by itself: the definitions are `deploy/cloudrun/*.yaml`, rendered by
`render.py` and sent by `deploy_service.py`.
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = "allUsers"

#: Service short name -> definition file, runtime account, callers, secrets it may read.
SERVICES: dict[str, dict] = {
    "qa": {"file": "qa.yaml", "sa": "run-qa", "secrets": ["db-role-qa-password", "gemini-api-key"]},
    "sentiment": {
        "file": "sentiment.yaml",
        "sa": "run-sentiment",
        "secrets": ["db-role-sentiment-password", "gemini-api-key"],
    },
    "forecast": {
        "file": "forecast.yaml",
        "sa": "run-forecast",
        "secrets": ["db-role-forecast-password", "gemini-api-key"],
    },
    "reporting": {
        "file": "reporting.yaml",
        "sa": "run-reporting",
        "secrets": ["db-role-reporting-password", "gemini-api-key"],
    },
    "orchestrator": {
        "file": "orchestrator.yaml",
        "sa": "run-orchestrator",
        "secrets": ["gemini-api-key"],
    },
    "gateway": {
        "file": "gateway.yaml",
        "sa": "run-gateway",
        "secrets": ["gateway-session-key", "gateway-invites"],
    },
}
DEPLOY_ORDER = ["qa", "sentiment", "forecast", "reporting", "orchestrator", "gateway"]
#: service -> the one account (short name) that may invoke it; the gateway is public.
INVOKER = {
    "qa": "run-orchestrator",
    "sentiment": "run-orchestrator",
    "forecast": "run-orchestrator",
    "reporting": "run-orchestrator",
    "orchestrator": "run-gateway",
    "gateway": PUBLIC,
}
NEW_ACCOUNTS = ["run-sentiment", "run-forecast", "run-qa", "run-gateway"]
CLOUDSQL_CLIENTS = ["run-sentiment", "run-forecast", "run-qa"]  # reporting's already holds it
ALL_RUNTIME = ["run-orchestrator", "run-reporting", *NEW_ACCOUNTS]


@dataclass(frozen=True)
class Config:
    project_id: str = "a2a-agentic-service-ops-gcp"
    project_number: str = "587647038690"
    region: str = "us-central1"
    ar_repo: str = "agentic-service-ops"
    instance: str = "ops-db"
    postgres_db: str = "service_ops"
    build_sa: str = "build-deploy"
    model: str = "gemini-3.5-flash-lite"
    image_tag: str = "<COMMIT_SHA>"

    def sa(self, short: str) -> str:
        return f"{short}@{self.project_id}.iam.gserviceaccount.com"

    @property
    def cloud_sql_instance(self) -> str:
        return f"{self.project_id}:{self.region}:{self.instance}"

    def render_env(self) -> dict[str, str]:
        """The placeholders `render.py` resolves (see deploy/cloudrun/*.yaml)."""
        return {
            "PROJECT_ID": self.project_id,
            "PROJECT_NUMBER": self.project_number,
            "REGION": self.region,
            "AR_REPO": self.ar_repo,
            "IMAGE_TAG": self.image_tag,
            "CLOUD_SQL_INSTANCE": self.cloud_sql_instance,
            "POSTGRES_DB": self.postgres_db,
            "GEMINI_MODEL_ORCHESTRATOR": self.model,
            "GEMINI_MODEL_SPECIALIST": self.model,
            "GEMINI_MODEL_QA": self.model,
            "ORCHESTRATOR_SA": self.sa("run-orchestrator"),
            "REPORTING_SA": self.sa("run-reporting"),
            "SENTIMENT_SA": self.sa("run-sentiment"),
            "FORECAST_SA": self.sa("run-forecast"),
            "QA_SA": self.sa("run-qa"),
            "GATEWAY_SA": self.sa("run-gateway"),
        }


@dataclass(frozen=True)
class Step:
    id: str
    phase: str
    title: str
    #: Commands, each an argv list; run in order. Empty for a pure note.
    commands: tuple[tuple[str, ...], ...] = ()
    #: Read-only command: exit 0 means the thing exists and the step is skipped.
    check: tuple[str, ...] | None = None
    #: What is piped to the first command's stdin ("token" = a new random key); never printed.
    stdin: str | None = None
    blocked: str | None = None
    #: For a deploy step: the service it deploys (the tests read these, not the command text).
    service: str | None = None
    #: For a binding step: (service, member short name or "allUsers").
    binding: tuple[str, str] | None = None
    #: For a secret-access step: (secret, account short name).
    secret_access: tuple[str, str] | None = None
    notes: tuple[str, ...] = field(default=())


def _gcloud(cfg: Config, *args: str) -> tuple[str, ...]:
    return ("gcloud", *args, "--project", cfg.project_id)


def build_plan(cfg: Config) -> list[Step]:
    steps: list[Step] = []

    for short in NEW_ACCOUNTS:
        steps.append(
            Step(
                id=f"sa-{short}",
                phase="1 service accounts",
                title=f"create {short}",
                commands=(
                    _gcloud(
                        cfg, "iam", "service-accounts", "create", short, "--display-name", short
                    ),
                ),
                check=_gcloud(cfg, "iam", "service-accounts", "describe", cfg.sa(short)),
            )
        )

    steps.append(
        Step(
            id="secret-gateway-session-key",
            phase="2 secrets",
            title="create gateway-session-key from 48 random bytes, piped (never on disk)",
            commands=(
                _gcloud(
                    cfg,
                    "secrets",
                    "create",
                    "gateway-session-key",
                    "--replication-policy",
                    "automatic",
                    "--data-file=-",
                ),
            ),
            check=_gcloud(cfg, "secrets", "describe", "gateway-session-key"),
            stdin="token",
        )
    )
    steps.append(
        Step(
            id="secret-gateway-invites",
            phase="2 secrets",
            title='create gateway-invites holding {"invites": []}',
            commands=(
                _gcloud(
                    cfg,
                    "secrets",
                    "create",
                    "gateway-invites",
                    "--replication-policy",
                    "automatic",
                    "--data-file=-",
                ),
            ),
            check=_gcloud(cfg, "secrets", "describe", "gateway-invites"),
            stdin='{"invites": []}',
        )
    )

    for name in DEPLOY_ORDER:
        svc = SERVICES[name]
        for secret in svc["secrets"]:
            steps.append(
                Step(
                    id=f"access-{secret}-{svc['sa']}",
                    phase="3 secret access (per secret, never project-wide)",
                    title=f"{svc['sa']} may read {secret}",
                    commands=(
                        _gcloud(
                            cfg,
                            "secrets",
                            "add-iam-policy-binding",
                            secret,
                            "--member",
                            f"serviceAccount:{cfg.sa(svc['sa'])}",
                            "--role",
                            "roles/secretmanager.secretAccessor",
                        ),
                    ),
                    secret_access=(secret, svc["sa"]),
                )
            )

    for short in CLOUDSQL_CLIENTS:
        steps.append(
            Step(
                id=f"cloudsql-{short}",
                phase="4 project roles",
                title=f"{short}: roles/cloudsql.client",
                commands=(
                    _gcloud(
                        cfg,
                        "projects",
                        "add-iam-policy-binding",
                        cfg.project_id,
                        "--member",
                        f"serviceAccount:{cfg.sa(short)}",
                        "--role",
                        "roles/cloudsql.client",
                        "--condition=None",
                    ),
                ),
            )
        )

    for short in NEW_ACCOUNTS:
        steps.append(
            Step(
                id=f"build-user-{short}",
                phase="5 build account",
                title=f"{cfg.build_sa} may deploy as {short} (serviceAccountUser)",
                commands=(
                    _gcloud(
                        cfg,
                        "iam",
                        "service-accounts",
                        "add-iam-policy-binding",
                        cfg.sa(short),
                        "--member",
                        f"serviceAccount:{cfg.sa(cfg.build_sa)}",
                        "--role",
                        "roles/iam.serviceAccountUser",
                    ),
                ),
            )
        )

    out = "rendered"
    for name in DEPLOY_ORDER:
        svc = SERVICES[name]
        blocked = svc.get("blocked")
        steps.append(
            Step(
                id=f"deploy-{name}",
                phase="6 services (dependency order)",
                title=f"render and deploy ops-{name}",
                commands=(
                    (
                        "python",
                        "deploy/render.py",
                        f"deploy/cloudrun/{svc['file']}",
                        f"{out}/{name}.json",
                    ),
                    ("python", "deploy/deploy_service.py", f"{out}/{name}.json"),
                ),
                check=None,
                blocked=blocked,
                service=name,
            )
        )
        member = INVOKER[name]
        who = "allUsers" if member == PUBLIC else f"serviceAccount:{cfg.sa(member)}"
        steps.append(
            Step(
                id=f"invoker-{name}",
                phase="6 services (dependency order)",
                title=f"ops-{name}: roles/run.invoker for {member}",
                commands=(
                    _gcloud(
                        cfg,
                        "run",
                        "services",
                        "add-iam-policy-binding",
                        f"ops-{name}",
                        "--region",
                        cfg.region,
                        "--member",
                        who,
                        "--role",
                        "roles/run.invoker",
                    ),
                ),
                blocked=blocked,
                binding=(name, member),
            )
        )
        if name == "orchestrator":
            steps.append(
                Step(
                    id="invoker-orchestrator-build",
                    phase="6 services (dependency order)",
                    title=f"ops-orchestrator: roles/run.invoker for {cfg.build_sa} (verify step)",
                    commands=(
                        _gcloud(
                            cfg,
                            "run",
                            "services",
                            "add-iam-policy-binding",
                            "ops-orchestrator",
                            "--region",
                            cfg.region,
                            "--member",
                            f"serviceAccount:{cfg.sa(cfg.build_sa)}",
                            "--role",
                            "roles/run.invoker",
                        ),
                    ),
                    binding=("orchestrator", cfg.build_sa),
                )
            )
    return steps


def select(steps: list[Step], phases: str | None, skip_deploy: bool) -> list[Step]:
    """`phases` is a comma list of phase numbers (`1,2,3,4,5`); `skip_deploy` drops the render
    and deploy steps and keeps the invoker bindings, for the run where Cloud Build deployed."""
    wanted = {p.strip() for p in phases.split(",")} if phases else None
    out = []
    for step in steps:
        if wanted is not None and step.phase.split()[0] not in wanted:
            continue
        if skip_deploy and step.id.startswith("deploy-"):
            continue
        out.append(step)
    return out


def format_step(index: int, step: Step) -> str:
    head = f"[{index:02d}] {step.phase} :: {step.title}"
    if step.blocked:
        head += f"  ** BLOCKED ({step.blocked}) **"
    lines = [head]
    if step.check:
        lines.append("     check (skip if it succeeds): " + " ".join(step.check))
    for command in step.commands:
        lines.append("     $ " + " ".join(command))
    if step.stdin == "token":
        lines.append("     stdin: secrets.token_urlsafe(48), generated at run time, not printed")
    elif step.stdin:
        lines.append(f"     stdin: {step.stdin}")
    return "\n".join(lines)


def run_plan(
    steps: list[Step],
    cfg: Config,
    run=subprocess.run,
    generate=lambda: secrets.token_urlsafe(48),
    out=print,
) -> int:
    """Execute the plan. `run` and `generate` are injected for the tests."""
    env = {**os.environ, **cfg.render_env()}
    for index, step in enumerate(steps, 1):
        if step.blocked:
            out(f"[{index:02d}] SKIP (blocked: {step.blocked}): {step.title}")
            continue
        if step.check is not None:
            done = run(list(step.check), capture_output=True, text=True, env=env, cwd=ROOT)
            if done.returncode == 0:
                out(f"[{index:02d}] exists, skipped: {step.title}")
                continue
        payload = (generate() if step.stdin == "token" else step.stdin) if step.stdin else None
        for n, command in enumerate(step.commands):
            argv = [sys.executable if command[0] == "python" else command[0], *command[1:]]
            result = run(
                argv,
                input=payload if n == 0 else None,
                text=True,
                env=env,
                cwd=ROOT,
                shell=sys.platform == "win32" and command[0] == "gcloud",
            )
            if result.returncode != 0:
                out(f"[{index:02d}] FAILED: {step.title}")
                return 1
        out(f"[{index:02d}] done: {step.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan_full.py")
    parser.add_argument("--dry-run", action="store_true", help="print the steps; no API call")
    parser.add_argument("--phases", help="comma list of phase numbers to include, e.g. 1,2,3,4,5")
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="leave out render and deploy (Cloud Build deployed); keep the invoker bindings",
    )
    parser.add_argument("--image-tag", default="<COMMIT_SHA>")
    parser.add_argument("--project-id", default=Config.project_id)
    parser.add_argument("--project-number", default=Config.project_number)
    parser.add_argument("--region", default=Config.region)
    args = parser.parse_args(argv)
    cfg = Config(
        project_id=args.project_id,
        project_number=args.project_number,
        region=args.region,
        image_tag=args.image_tag,
    )
    steps = select(build_plan(cfg), args.phases, args.skip_deploy)
    if args.dry_run:
        for index, step in enumerate(steps, 1):
            print(format_step(index, step))
        print(f"\n{len(steps)} steps; {sum(1 for s in steps if s.blocked)} blocked. Dry run: done.")
        return 0
    if not args.skip_deploy and cfg.image_tag.startswith("<"):
        print("error: --image-tag is required to run the plan", file=sys.stderr)
        return 2
    return run_plan(steps, cfg)


if __name__ == "__main__":
    sys.exit(main())
