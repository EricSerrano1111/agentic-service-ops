"""The access matrix says what `docs/data-dictionary.md` §7 says.

§7 names three properties that a database grant enforces and a code convention would
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
    [am.ROLE_REPORTING, am.ROLE_SENTIMENT, am.ROLE_FORECAST, am.ROLE_QA],
)
def test_no_agent_role_reaches_pii(role: str) -> None:
    """§7 point 3: customer PII never enters an LLM context window.

    `contacts` and `internal_users` are reachable only by the generator, which is an
    offline script rather than an agent.
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


def test_forecast_sees_neither_incidents_nor_sentiment() -> None:
    """ADR-018: the forecast is univariate — date in, volume out.

    This is also what makes the severity→sentiment coupling in ADR-021 safe: there
    is no path for the forecast to learn a shortcut from data it cannot reach.
    """
    readable = am.tables_readable_by(am.ROLE_FORECAST)
    assert not (readable & {"incidents", "service_feedback", "sentiment_labels"})


def test_qa_can_cross_check_every_specialist() -> None:
    """§7: QA is deliberately broad — verification needs what specialists can't see."""
    readable = am.tables_readable_by(am.ROLE_QA)
    for table in (
        "incidents",
        "service_feedback",
        "sentiment_labels",
        "generation_parameters",
        "service_requests",
        "archived_requests",
    ):
        assert table in readable


def test_every_role_has_an_env_var_pair() -> None:
    for role in am.ALL_ROLES:
        user_var, password_var = am.ROLE_ENV_VARS[role]
        assert user_var.endswith("_USER")
        assert password_var.endswith("_PASSWORD")
