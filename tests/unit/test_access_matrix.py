"""The access matrix says what `docs/data-dictionary.md` §7 says.

§7 names seven properties that a database grant enforces and a code convention would
not. Each has a test here, so a future edit to the matrix that quietly reopens one of
them fails CI rather than shipping.

These assert the *intent* encoded in `db_models.access_matrix`. That the database
actually ends up in that state is proven separately by connecting as each role after
`alembic upgrade head` — see `tests/integration/test_access_matrix_grants.py`.
"""

from __future__ import annotations

import db_models as m
import pytest
from db_models import access_matrix as am


def test_matrix_covers_exactly_the_modelled_tables() -> None:
    assert set(am.ALL_TABLES) == set(m.metadata.tables)


def test_every_referenced_table_exists() -> None:
    """Guards against a typo silently granting nothing."""
    for role in am.ALL_ROLES:
        unknown = am.tables_readable_by(role) - set(m.metadata.tables)
        assert not unknown, f"{role} references non-existent table(s): {sorted(unknown)}"


def test_sentiment_agent_cannot_read_its_own_ground_truth() -> None:
    """§7 point 1: circular self-verification is structurally impossible."""
    assert "sentiment_labels" not in am.tables_readable_by(am.ROLE_SENTIMENT)


def test_sentiment_agent_cannot_read_incidents() -> None:
    """§7 point 2: staff-written notes can never leak into the sentiment pipeline."""
    assert "incidents" not in am.tables_readable_by(am.ROLE_SENTIMENT)


def test_sentiment_agent_reads_only_service_feedback() -> None:
    """The sentiment MCP server's entire world is one table."""
    assert am.tables_readable_by(am.ROLE_SENTIMENT) == {"service_feedback"}


@pytest.mark.parametrize(
    "role",
    [
        am.ROLE_REPORTING,
        am.ROLE_SENTIMENT,
        am.ROLE_FORECAST,
        am.ROLE_QA,
        am.ROLE_EVAL,
        am.ROLE_TRAIN,
    ],
)
def test_no_agent_role_reaches_pii(role: str) -> None:
    """§7 point 3: customer PII never enters an LLM context window.

    `contacts` and `internal_users` are reachable only by the generator, which is an
    offline script rather than an agent. The offline read roles are held to the same
    rule: evaluation and training never need PII (ADR-063).
    """
    assert not (am.tables_readable_by(role) & am.PII_RESTRICTED_TABLES)


def test_generator_is_the_only_writer() -> None:
    assert set(am.ALL_GRANTS) == {am.ROLE_GENERATOR}
    assert am.ALL_GRANTS[am.ROLE_GENERATOR] == set(am.ALL_TABLES)


def test_reporting_cannot_read_raw_feedback_text() -> None:
    """§7's "SELECT (aggregate)" on service_feedback, enforced by column.

    Postgres has no aggregate-only privilege. Omitting `feedback_text` from a
    column-level grant is what makes the documented boundary and the actual
    boundary the same thing.
    """
    assert "service_feedback" not in am.SELECT_GRANTS[am.ROLE_REPORTING]

    granted = set(am.COLUMN_SELECT_GRANTS[am.ROLE_REPORTING]["service_feedback"])
    assert "feedback_text" not in granted

    # And it is the *only* column withheld — reporting still aggregates ratings.
    all_columns = set(m.metadata.tables["service_feedback"].columns.keys())
    assert all_columns - granted == {"feedback_text"}


def test_sentiment_cannot_read_rating() -> None:
    """§7 point 4 / R-04 / ADR-027: rating stays an independent cross-check on sentiment.

    The column set is pinned exactly, so widening it is a deliberate, reviewed change
    rather than a drive-by addition.
    """
    assert "service_feedback" not in am.SELECT_GRANTS[am.ROLE_SENTIMENT]

    granted = set(am.COLUMN_SELECT_GRANTS[am.ROLE_SENTIMENT]["service_feedback"])
    assert granted == {"feedback_id", "request_id", "submitted_at", "feedback_text"}
    assert "rating" not in granted


def test_forecast_sees_neither_incidents_nor_sentiment() -> None:
    """ADR-018: the forecast is univariate — date in, volume out.

    This is also what makes the severity→sentiment coupling in ADR-021 safe: there
    is no path for the forecast to learn a shortcut from data it cannot reach.
    """
    readable = am.tables_readable_by(am.ROLE_FORECAST)
    assert not (readable & {"incidents", "service_feedback", "sentiment_labels"})


def test_forecast_reads_only_service_requests() -> None:
    """ADR-035: the forecast MCP server's entire world is one table."""
    assert am.tables_readable_by(am.ROLE_FORECAST) == {"service_requests"}


@pytest.mark.parametrize("table", ["accounts", "locations", "archived_requests"])
def test_forecast_cannot_read_accounts_locations_or_archive(table: str) -> None:
    """ADR-035: dropped from the original §7 forecast column — none is used by the series."""
    assert table not in am.tables_readable_by(am.ROLE_FORECAST)


def test_forecast_reads_exactly_three_request_columns() -> None:
    """§7 point 5 / ADR-035: no billing, no customer or technician identifier.

    The column set is pinned exactly, so widening it (a regional or per-account
    breakout, say) is a deliberate, reviewed change rather than a drive-by addition.
    """
    assert "service_requests" not in am.SELECT_GRANTS[am.ROLE_FORECAST]

    granted = set(am.COLUMN_SELECT_GRANTS[am.ROLE_FORECAST]["service_requests"])
    assert granted == {"request_id", "scheduled_datetime", "service_type"}
    assert granted <= set(m.metadata.tables["service_requests"].columns.keys())


def test_qa_can_cross_check_every_specialist() -> None:
    """§7: QA is deliberately broad — verification needs what specialists can't see."""
    readable = am.tables_readable_by(am.ROLE_QA)
    for table in (
        "incidents",
        "service_feedback",
        "service_requests",
        "archived_requests",
    ):
        assert table in readable


def test_qa_reads_exactly_the_operational_tables_minus_pii() -> None:
    """§7 / ADR-063: every operational table except PII, all in full, nothing else."""
    assert am.tables_readable_by(am.ROLE_QA) == {
        "accounts",
        "locations",
        "technicians",
        "technician_skills",
        "service_requests",
        "archived_requests",
        "incidents",
        "service_feedback",
    }
    assert am.ROLE_QA not in am.COLUMN_SELECT_GRANTS


@pytest.mark.parametrize("table", ["sentiment_labels", "generation_parameters"])
def test_runtime_qa_cannot_read_gold_labels_or_generator_parameters(table: str) -> None:
    """§7 point 6 / ADR-055 / ADR-063: answers in a real deployment have no gold labels,
    so the runtime QA role never ships holding them."""
    assert table not in am.tables_readable_by(am.ROLE_QA)


@pytest.mark.parametrize(
    "role", [am.ROLE_REPORTING, am.ROLE_SENTIMENT, am.ROLE_FORECAST, am.ROLE_QA]
)
@pytest.mark.parametrize("table", ["sentiment_labels", "generation_parameters"])
def test_no_runtime_role_reads_ground_truth(role: str, table: str) -> None:
    """ADR-062 / ADR-063: ground truth is read only by offline roles."""
    assert table not in am.tables_readable_by(role)


def test_eval_reads_what_qa_held_before_adr_063() -> None:
    """ADR-063: the ten tables app_qa held before the revoke, all in full."""
    assert (
        am.tables_readable_by(am.ROLE_EVAL)
        == am.SELECT_GRANTS[am.ROLE_EVAL]
        == {
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
    )
    assert am.ROLE_EVAL not in am.COLUMN_SELECT_GRANTS


def test_train_reads_labels_and_exactly_what_inference_reads() -> None:
    """§7 point 7 / ADR-063: labels in full; feedback and requests by the runtime columns."""
    assert am.SELECT_GRANTS[am.ROLE_TRAIN] == {"sentiment_labels"}
    assert am.COLUMN_SELECT_GRANTS[am.ROLE_TRAIN] == {
        "service_feedback": am.COLUMN_SELECT_GRANTS[am.ROLE_SENTIMENT]["service_feedback"],
        "service_requests": am.COLUMN_SELECT_GRANTS[am.ROLE_FORECAST]["service_requests"],
    }
    assert am.tables_readable_by(am.ROLE_TRAIN) == {
        "sentiment_labels",
        "service_feedback",
        "service_requests",
    }


def test_train_cannot_read_rating_or_generator_parameters() -> None:
    """§7 point 7: a model trained on the stars would undermine QA's rating cross-check
    (R-04, ADR-027); the parameters are the forecast's answer key (ADR-058)."""
    feedback = set(am.COLUMN_SELECT_GRANTS[am.ROLE_TRAIN]["service_feedback"])
    assert feedback == {"feedback_id", "request_id", "submitted_at", "feedback_text"}
    assert "rating" not in feedback
    readable = am.tables_readable_by(am.ROLE_TRAIN)
    assert not (readable & {"generation_parameters", "incidents", "contacts"})


def test_offline_read_roles_are_eval_and_train() -> None:
    assert set(am.OFFLINE_READ_ROLES) == {am.ROLE_EVAL, am.ROLE_TRAIN}
    assert set(am.OFFLINE_READ_ROLES) <= set(am.ALL_ROLES)


def test_every_role_has_an_env_var_pair() -> None:
    for role in am.ALL_ROLES:
        user_var, password_var = am.ROLE_ENV_VARS[role]
        assert user_var.endswith("_USER")
        assert password_var.endswith("_PASSWORD")
