"""The feedback MCP server: sentiment answers from stored predictions, over streamable HTTP.

No generic query tool, ever (ADR-023), and no tool that writes: storing predictions is
internal (`ensure_scored`), never something a caller asks for. Every input is validated
against types and vocabularies before any query runs. Streamable HTTP in stateless mode,
as `mcp_incidents`.

Tools (ADR-067):
- `get_sentiment_summary`: counts and shares by label, flag count, and per-bucket counts.
  No comment text.
- `get_feedback_examples`: at most 5 comments with text, for citation.

Both score unscored comments in range first (at most the cap, newest first) and report
coverage: `n_comments`, `n_scored`, `complete`.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

import anyio
from common import TRACE_ID_KEY, bind_trace_id
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from schemas import (
    MAX_EXAMPLES,
    MAX_SPAN_DAYS,
    SENTIMENT_LABELS,
    Bucket,
    FeedbackExample,
    FeedbackExamples,
    SentimentLabel,
    SentimentSummary,
    SiteRegion,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from .classifier import Classifier
from .config import Settings
from .scoring import Scope, Store, build_summary, ensure_scored

log = logging.getLogger("mcp_feedback")

SUMMARY = "get_sentiment_summary"
EXAMPLES = "get_feedback_examples"
_REGIONS = ("northeast", "southeast", "central", "west")

Start = Annotated[str, Field(description="First day, inclusive: YYYY-MM-DD (UTC).")]
End = Annotated[str, Field(description="Last day, inclusive: YYYY-MM-DD (UTC).")]
RegionArg = Annotated[SiteRegion | None, Field(description="Optional: the customer site's region.")]


class InvalidInput(ValueError):
    """A caller error: the message is safe to return to the client verbatim. `argument` and
    `kind` say which argument was rejected and why, with no value: they are what the log
    records, since a rejected value may be text from a user's question."""

    def __init__(self, message: str, *, argument: str, kind: str) -> None:
        super().__init__(message)
        self.argument = argument
        self.kind = kind


def _parse_date(name: str, raw: str) -> dt.date:
    if not isinstance(raw, str) or len(raw) != 10:
        raise InvalidInput(
            f"{name} must be an ISO date (YYYY-MM-DD)",
            argument=name,
            kind="not_iso_date",
        )
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise InvalidInput(
            f"{name} must be an ISO date (YYYY-MM-DD)",
            argument=name,
            kind="not_iso_date",
        ) from None


def parse_scope(
    start: str, end: str, region: str | None, window_start: dt.date, window_end: dt.date
) -> Scope:
    """Strict `YYYY-MM-DD`, start <= end, at most 731 days, inside the dataset window."""
    s, e = _parse_date("start", start), _parse_date("end", end)
    if s > e:
        raise InvalidInput(
            f"start ({s}) is after end ({e})", argument="start,end", kind="start_after_end"
        )
    if (e - s).days + 1 > MAX_SPAN_DAYS:
        raise InvalidInput(
            f"range {s} to {e} spans more than {MAX_SPAN_DAYS} days",
            argument="start,end",
            kind="span_too_long",
        )
    if s < window_start or e > window_end:
        raise InvalidInput(
            f"range {s} to {e} is outside the dataset window "
            f"{window_start} to {window_end} (inclusive)",
            argument="start,end",
            kind="outside_window",
        )
    if region is not None and region not in _REGIONS:
        raise InvalidInput(
            f"region must be one of {', '.join(_REGIONS)}",
            argument="region",
            kind="not_in_vocabulary",
        )
    return Scope(s, e, region)


def check_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_EXAMPLES:
        raise InvalidInput(
            f"limit must be an integer from 1 to {MAX_EXAMPLES}",
            argument="limit",
            kind="out_of_range",
        )
    return limit


@dataclass(frozen=True)
class Backend:
    """What the tools run on. Offline tests pass an in-memory store and a stub classifier."""

    store: Store
    classifier: Classifier
    model_version: str
    score_cap: int
    ready: Callable[[], None]


def create_server(settings: Settings, backend: Backend) -> MCPServer:
    server = MCPServer(
        "mcp_feedback",
        instructions="Customer-feedback sentiment for the field-service dataset, from stored "
        "model predictions. Summaries carry no text; examples return at most 5 comments.",
        version="0.1.0",
    )

    async def run(tool: str, ctx: Context, validate: Callable[[], Any], answer: Callable) -> Any:
        """Validate, score what's missing, answer from storage; log; map errors."""
        meta = ctx.request_context.meta or {}
        with bind_trace_id(meta.get(TRACE_ID_KEY)):
            try:
                args = validate()
            except InvalidInput as exc:
                log.info(
                    "tool rejected input",
                    extra={"tool": tool, "argument": exc.argument, "error_type": exc.kind},
                )
                raise ToolError(str(exc)) from None
            began = time.perf_counter()
            try:
                result, coverage = await anyio.to_thread.run_sync(answer, *args)
            except Exception:
                # Log the cause here; the client gets a generic message, never SQL detail.
                log.exception("tool query failed", extra={"tool": tool})
                raise ToolError("feedback query failed") from None
            log.info(
                "tool call",
                extra={
                    "tool": tool,
                    "start": args[0].start.isoformat(),
                    "end": args[0].end.isoformat(),
                    "region": args[0].region,
                    "n_comments": coverage.n_comments,
                    "n_scored": coverage.n_scored,
                    "n_scored_now": coverage.n_new,
                    "complete": coverage.complete,
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            return result

    def _coverage(scope: Scope):
        return ensure_scored(
            backend.store, backend.classifier, backend.model_version, scope, backend.score_cap
        )

    def summary(scope: Scope, bucket: str):
        coverage = _coverage(scope)
        rows = backend.store.label_bucket_counts(backend.model_version, scope, bucket)
        return build_summary(backend.model_version, scope, bucket, coverage, rows), coverage

    def examples(scope: Scope, label: str | None, flagged_only: bool, limit: int):
        coverage = _coverage(scope)
        rows = backend.store.examples(backend.model_version, scope, label, flagged_only, limit)
        result = FeedbackExamples(
            model_version=backend.model_version,
            n_comments=coverage.n_comments,
            n_scored=coverage.n_scored,
            complete=coverage.complete,
            start=scope.start,
            end=scope.end,
            region=scope.region,
            label=label,
            flagged_only=flagged_only,
            examples=[
                FeedbackExample(
                    feedback_id=r.feedback_id,
                    submitted_at=r.submitted_at,
                    region=r.region,
                    label=r.label,
                    confidence=f"{r.confidence:.4f}",
                    flagged=r.flagged,
                    feedback_text=r.feedback_text,
                )
                for r in rows
            ],
        )
        return result, coverage

    def scope_of(start: str, end: str, region: str | None) -> Scope:
        return parse_scope(start, end, region, settings.window_start, settings.window_end)

    @server.tool(name=SUMMARY)
    async def get_sentiment_summary(
        start: Start,
        end: End,
        ctx: Context,
        region: RegionArg = None,
        bucket: Annotated[Bucket, Field(description="month (default) or quarter.")] = "month",
    ) -> SentimentSummary:
        """Sentiment of customer feedback submitted in a date range, optionally one region.

        Counts and shares by label (positive, neutral, negative, mixed), the number of
        comments flagged for human review (low model confidence), and counts per month or
        quarter. Answers from stored model predictions; comments in range without one are
        scored first, at most 250 per call, newest first. If `complete` is false, the
        figures cover only `n_scored` of `n_comments` and must be reported that way.
        No comment text.
        """

        def validate():
            if bucket not in ("month", "quarter"):
                raise InvalidInput(
                    "bucket must be month or quarter",
                    argument="bucket",
                    kind="not_in_vocabulary",
                )
            return scope_of(start, end, region), bucket

        return await run(SUMMARY, ctx, validate, summary)

    @server.tool(name=EXAMPLES)
    async def get_feedback_examples(
        start: Start,
        end: End,
        ctx: Context,
        region: RegionArg = None,
        label: Annotated[
            SentimentLabel | None, Field(description="Optional: only this predicted label.")
        ] = None,
        flagged_only: Annotated[
            bool, Field(description="Only comments flagged for human review.")
        ] = False,
        limit: Annotated[int, Field(description="How many, 1 to 5.")] = MAX_EXAMPLES,
    ) -> FeedbackExamples:
        """Up to 5 customer comments with their text, for quoting in an answer.

        Most confident first (ties by lowest id); with `flagged_only`, least confident
        first. Same range, region and scoring rules as `get_sentiment_summary`.
        """

        def validate():
            if label is not None and label not in SENTIMENT_LABELS:
                raise InvalidInput(
                    f"label must be one of {', '.join(SENTIMENT_LABELS)}",
                    argument="label",
                    kind="not_in_vocabulary",
                )
            if not isinstance(flagged_only, bool):
                raise InvalidInput(
                    "flagged_only must be true or false",
                    argument="flagged_only",
                    kind="wrong_type",
                )
            return scope_of(start, end, region), label, flagged_only, check_limit(limit)

        return await run(EXAMPLES, ctx, validate, examples)

    @server.custom_route("/healthz", methods=["GET"])
    @server.custom_route("/readyz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        """Ready: the artifact hashes verified at start-up and the database answers.

        `/readyz` is the same check under the name the Cloud Run probes use.
        """
        try:
            await anyio.to_thread.run_sync(backend.ready)
        except Exception:
            log.warning("readiness check failed: database unreachable")
            return JSONResponse(
                {"status": "unavailable", "service": "mcp_feedback"}, status_code=503
            )
        return JSONResponse(
            {"status": "ok", "service": "mcp_feedback", "model_version": backend.model_version}
        )

    return server


def create_app(settings: Settings, backend: Backend) -> Starlette:
    server = create_server(settings, backend)
    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,  # blocking request/response; nothing here streams
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[],
        ),
    )
