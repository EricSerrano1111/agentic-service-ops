"""The §7 table → role access matrix, as data.

`docs/data-dictionary.md` §7 specifies per-agent database privileges. Transcribing it
into a wall of GRANT statements would make the security boundary unreviewable and
undiffable. It lives here instead as a single structure the tests assert against: the
unit tests check it says what §7 says, and the integration tests check the migrated
database grants exactly this. Migrations do *not* import it — each carries a frozen
literal copy of the grants it applied (ADR-027), so a change here needs a new migration
or the integration suite fails.

The constants below are the canonical role keys — the names `.env` ships with and the
documentation uses. The actual name each role is created under comes from
`DB_ROLE_*_USER`, which is required rather than defaulted: see
`_resolve_credentials()` in the roles migration.

Seven properties this matrix enforces structurally, which a code convention would not
(§7):

1. `app_sentiment` cannot read `sentiment_labels` — self-verification is impossible.
2. `app_sentiment` cannot read `incidents` — staff-written notes cannot leak into the
   sentiment pipeline.
3. No role but the generator touches `contacts` — customer PII never reaches an LLM
   context window.
4. `app_sentiment` cannot read `service_feedback.rating` — the rating stays an
   independent cross-check on sentiment for the QA agent (R-04, ADR-027).
5. `app_forecast` cannot read billing or any customer or technician identifier — it
   sees three columns of `service_requests` and nothing else (ADR-035).
6. `app_qa` cannot read `sentiment_labels` or `generation_parameters` — the runtime QA
   role never holds gold labels or the generator's answer key (ADR-055, ADR-063).
7. `app_train` cannot read `service_feedback.rating` or `generation_parameters` — a
   model trained on the stars would undermine QA's rating cross-check, and the
   parameters are the forecast's answer key (ADR-058, ADR-063).

`app_eval` and `app_train` are offline read roles: they are used only by scripts on the
developer machine and are never held by a deployed service (ADR-063).
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #

ROLE_REPORTING: Final = "app_reporting"
ROLE_SENTIMENT: Final = "app_sentiment"
ROLE_FORECAST: Final = "app_forecast"
ROLE_QA: Final = "app_qa"
ROLE_GENERATOR: Final = "app_generator"
ROLE_EVAL: Final = "app_eval"
ROLE_TRAIN: Final = "app_train"

#: Role → the environment variable pair carrying its name and password.
ROLE_ENV_VARS: Final[dict[str, tuple[str, str]]] = {
    ROLE_REPORTING: ("DB_ROLE_REPORTING_USER", "DB_ROLE_REPORTING_PASSWORD"),
    ROLE_SENTIMENT: ("DB_ROLE_SENTIMENT_USER", "DB_ROLE_SENTIMENT_PASSWORD"),
    ROLE_FORECAST: ("DB_ROLE_FORECAST_USER", "DB_ROLE_FORECAST_PASSWORD"),
    ROLE_QA: ("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"),
    ROLE_GENERATOR: ("DB_ROLE_GENERATOR_USER", "DB_ROLE_GENERATOR_PASSWORD"),
    ROLE_EVAL: ("DB_ROLE_EVAL_USER", "DB_ROLE_EVAL_PASSWORD"),
    ROLE_TRAIN: ("DB_ROLE_TRAIN_USER", "DB_ROLE_TRAIN_PASSWORD"),
}

ALL_ROLES: Final[tuple[str, ...]] = tuple(ROLE_ENV_VARS)

#: Read-only roles for offline scripts on the developer machine (validation, evaluation,
#: training). No deployed service, compose file or Dockerfile may reference their
#: credentials (ADR-063); `tests/unit/test_offline_roles_isolation.py` asserts that.
OFFLINE_READ_ROLES: Final[tuple[str, ...]] = (ROLE_EVAL, ROLE_TRAIN)

#: Every table in the schema. The generator holds ALL on each of these.
ALL_TABLES: Final[tuple[str, ...]] = (
    "accounts",
    "contacts",
    "locations",
    "technicians",
    "technician_skills",
    "internal_users",
    "service_requests",
    "archived_requests",
    "incidents",
    "service_feedback",
    "sentiment_labels",
    "generation_parameters",
)

# --------------------------------------------------------------------------- #
# Table-level SELECT grants
# --------------------------------------------------------------------------- #

#: Role → tables it may SELECT in full. Transcribed row-by-row from §7.
#: Absence is the point: a table missing from a role's set means no privilege at all.
SELECT_GRANTS: Final[dict[str, frozenset[str]]] = {
    ROLE_REPORTING: frozenset(
        {
            "accounts",
            "locations",
            "technicians",
            "technician_skills",
            "service_requests",
            "archived_requests",
            "incidents",
            # service_feedback is column-level only — see COLUMN_SELECT_GRANTS.
        }
    ),
    ROLE_SENTIMENT: frozenset(),  # service_feedback is column-level only — see ADR-027.
    ROLE_FORECAST: frozenset(),  # service_requests is column-level only — see ADR-035.
    # Deliberately broad: verification requires cross-checking sources the
    # specialists cannot see. That also makes the QA agent the highest-value target
    # in the system, which the threat model addresses explicitly. Gold labels and
    # generator parameters are not among them: QA checks answers, and answers in a
    # real deployment have no gold labels (ADR-055, ADR-063).
    ROLE_QA: frozenset(
        {
            "accounts",
            "locations",
            "technicians",
            "technician_skills",
            "service_requests",
            "archived_requests",
            "incidents",
            "service_feedback",
        }
    ),
    ROLE_GENERATOR: frozenset(),  # covered by ALL_GRANTS below
    # Validation and evaluation: the ten tables app_qa held before ADR-063, gold
    # labels and generator parameters included. Never contacts or internal_users.
    ROLE_EVAL: frozenset(
        {
            "accounts",
            "locations",
            "technicians",
            "technician_skills",
            "service_requests",
            "archived_requests",
            "incidents",
            "service_feedback",
            "sentiment_labels",
            "generation_parameters",
        }
    ),
    # Training: the labels in full; everything else by column — see COLUMN_SELECT_GRANTS.
    ROLE_TRAIN: frozenset({"sentiment_labels"}),
}

#: Role → ALL PRIVILEGES tables.
ALL_GRANTS: Final[dict[str, frozenset[str]]] = {
    ROLE_GENERATOR: frozenset(ALL_TABLES),
}

# --------------------------------------------------------------------------- #
# Column-level SELECT grants
# --------------------------------------------------------------------------- #

#: Every column of `service_feedback` except `feedback_text`.
_FEEDBACK_NON_TEXT_COLUMNS: Final[tuple[str, ...]] = (
    "feedback_id",
    "request_id",
    "incident_id",
    "submitted_by_contact_id",
    "submitted_at",
    "rating",
    "response_channel",
    "created_at",
)

#: The sentiment agent's view of `service_feedback`: the text, an identifier to report
#: against, and the timestamp its batch pulls filter on. `rating` is withheld because it
#: is the QA agent's independent cross-check on sentiment (R-04) — a classifier that can
#: see the stars is no longer being checked independently. Withholding the rest drops a
#: PII foreign key (`submitted_by_contact_id`) and a pointer into staff-written data
#: (`incident_id`) as a side effect.
_SENTIMENT_FEEDBACK_COLUMNS: Final[tuple[str, ...]] = (
    "feedback_id",
    "request_id",
    "submitted_at",
    "feedback_text",
)

#: The forecast agent's view of `service_requests`: the date the univariate weekly
#: series is counted by (ADR-018), the optional `service_type` breakout, and an
#: identifier to count against. Everything else is withheld — billing and payment
#: fields, cancellation detail, and every account, contact and technician identifier.
#: A breakout beyond `service_type` is a new grant, migration and ADR (ADR-035).
_FORECAST_REQUEST_COLUMNS: Final[tuple[str, ...]] = (
    "request_id",
    "scheduled_datetime",
    "service_type",
)

#: Role → table → the specific columns it may SELECT.
#:
#: §7 marks reporting's access to `service_feedback` as "SELECT (aggregate)".
#: Postgres has no aggregate-only privilege, so the qualifier is honoured with a
#: column-level grant that omits `feedback_text`: the reporting agent can count and
#: average ratings, and is structurally unable to read a customer's raw words.
#: Enforcing it at the tool layer instead would leave the documented boundary and
#: the actual boundary out of step.
COLUMN_SELECT_GRANTS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    ROLE_REPORTING: {"service_feedback": _FEEDBACK_NON_TEXT_COLUMNS},
    ROLE_SENTIMENT: {"service_feedback": _SENTIMENT_FEEDBACK_COLUMNS},
    ROLE_FORECAST: {"service_requests": _FORECAST_REQUEST_COLUMNS},
    # Training reads exactly what the runtime models read, plus the labels (ADR-063):
    # no `rating` (it would undermine QA's rating cross-check) and no
    # `generation_parameters` (the forecast's answer key, ADR-058).
    ROLE_TRAIN: {
        "service_feedback": _SENTIMENT_FEEDBACK_COLUMNS,
        "service_requests": _FORECAST_REQUEST_COLUMNS,
    },
}

# --------------------------------------------------------------------------- #
# Invariants — asserted by tests, restated here so the intent travels with the data
# --------------------------------------------------------------------------- #

#: No role may hold any privilege on these, except the generator.
PII_RESTRICTED_TABLES: Final[frozenset[str]] = frozenset({"contacts", "internal_users"})


def tables_readable_by(role: str) -> frozenset[str]:
    """Every table `role` can read at all, whether in full or by column."""
    return (
        SELECT_GRANTS.get(role, frozenset())
        | frozenset(COLUMN_SELECT_GRANTS.get(role, {}))
        | ALL_GRANTS.get(role, frozenset())
    )
