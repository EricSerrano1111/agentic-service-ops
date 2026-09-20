"""The §7 table → role access matrix, as data.

`docs/data-dictionary.md` §7 specifies per-agent database privileges. Transcribing it
into a wall of GRANT statements would make the security boundary unreviewable and
undiffable. It lives here instead as a single structure that the roles migration
executes and the tests assert against, so the granted privileges and the documented
matrix cannot drift apart.

The constants below are the canonical role keys — the names `.env` ships with and the
documentation uses. The actual name each role is created under comes from
`DB_ROLE_*_USER`, which is required rather than defaulted: see
`_resolve_credentials()` in the roles migration.

Three properties this matrix enforces structurally, which a code convention would not
(§7):

1. `app_sentiment` cannot read `sentiment_labels` — self-verification is impossible.
2. `app_sentiment` cannot read `incidents` — staff-written notes cannot leak into the
   sentiment pipeline.
3. No role but the generator touches `contacts` — customer PII never reaches an LLM
   context window.
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

#: Role → the environment variable pair carrying its name and password.
ROLE_ENV_VARS: Final[dict[str, tuple[str, str]]] = {
    ROLE_REPORTING: ("DB_ROLE_REPORTING_USER", "DB_ROLE_REPORTING_PASSWORD"),
    ROLE_SENTIMENT: ("DB_ROLE_SENTIMENT_USER", "DB_ROLE_SENTIMENT_PASSWORD"),
    ROLE_FORECAST: ("DB_ROLE_FORECAST_USER", "DB_ROLE_FORECAST_PASSWORD"),
    ROLE_QA: ("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"),
    ROLE_GENERATOR: ("DB_ROLE_GENERATOR_USER", "DB_ROLE_GENERATOR_PASSWORD"),
}

ALL_ROLES: Final[tuple[str, ...]] = tuple(ROLE_ENV_VARS)

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
    ROLE_SENTIMENT: frozenset({"service_feedback"}),
    ROLE_FORECAST: frozenset(
        {
            "accounts",
            "locations",
            "service_requests",
            "archived_requests",
        }
    ),
    # Deliberately broad: verification requires cross-checking sources the
    # specialists cannot see. That also makes the QA agent the highest-value target
    # in the system, which the threat model addresses explicitly.
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
            "sentiment_labels",
            "generation_parameters",
        }
    ),
    ROLE_GENERATOR: frozenset(),  # covered by ALL_GRANTS below
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
