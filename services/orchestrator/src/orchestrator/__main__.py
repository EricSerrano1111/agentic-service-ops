"""`python -m orchestrator serve` runs the API; `python -m orchestrator ask "..."` calls it."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx
import uvicorn
from common import configure_logging

from .app import create_app
from .config import Settings

# ADR-034: anything in front of the orchestrator waits longer than the 120 s ceiling.
CLI_TIMEOUT_S = 130.0


def _serve() -> int:
    settings = Settings.from_env()
    configure_logging("orchestrator", os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)
    return 0


def _ask(question: str, url: str) -> int:
    try:
        response = httpx.post(f"{url}/ask", json={"question": question}, timeout=CLI_TIMEOUT_S)
    except httpx.HTTPError as exc:
        print(f"error: could not reach the orchestrator at {url}: {exc}", file=sys.stderr)
        return 2
    body = response.json()
    if response.is_success:
        route = body["route"]
        print(body["answer"])
        print(f"route={route['route']} ({route['reason']}) prompt={body['prompt_version']}")
        if body.get("reporting"):
            print(json.dumps(body["reporting"], indent=2))
        print(
            f"outcome={body['outcome']} task_id={body.get('task_id')} trace_id={body['trace_id']}"
        )
        return 0
    print(f"error {response.status_code}: {json.dumps(body, indent=2)}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the orchestrator API")
    ask = sub.add_parser("ask", help="send one question to a running orchestrator")
    ask.add_argument("question")
    ask.add_argument(
        "--url",
        default=os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000"),
        help="orchestrator base URL (default: $ORCHESTRATOR_URL or http://localhost:8000)",
    )
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve()
    return _ask(args.question, args.url.rstrip("/"))


if __name__ == "__main__":
    sys.exit(main())
