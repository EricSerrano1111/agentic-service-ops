"""The schema matches `docs/data-dictionary.md`, and the migration matches the models.

These run without a database. The end-to-end proof is still `alembic upgrade head`
followed by `alembic check` against real Postgres (see README), but these catch the
failure mode that matters most for a hand-written migration — a table, index or
constraint present in one place and missing from the other — on every commit.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import db_models as m
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parents[2]
INITIAL_REVISION = "0f3c81a47b21"

EXPECTED_TABLES = {
    # §2 reference
    "accounts",
    "contacts",
    "locations",
    "technicians",
    "technician_skills",
    "internal_users",
    # §3 operational
    "service_requests",
    "archived_requests",
    "incidents",
    "service_feedback",
    # §4 ground truth
    "sentiment_labels",
    "generation_parameters",
}

# §9 "Indexing considerations for the MCP tools". The listed
# service_feedback(request_id) index is intentionally absent: its UNIQUE constraint
# already provides an equivalent btree index.
EXPECTED_INDEXES = {
    "ix_service_requests_scheduled_datetime",
    "ix_service_requests_account_id_scheduled_datetime",
    "ix_service_requests_request_status",
    "ix_service_requests_parent_request_id",
    "ix_incidents_request_id",
    "ix_incidents_incident_type_reported_at",
    "ix_service_feedback_submitted_at",
    "ix_archived_requests_completed_at",
}

# §8 check constraints, plus the two additions noted in the migration docstring.
EXPECTED_CHECK_CONSTRAINTS = {
    "ck_service_feedback_rating_range",
    "ck_archived_requests_labor_charge_non_negative",
    "ck_archived_requests_parts_charge_non_negative",
    "ck_incidents_credit_issued_amount_non_negative",
    "ck_archived_requests_surcharge_rate_range",
    "ck_service_requests_equipment_unit_count_positive",
    "ck_service_requests_parent_not_self",
    "ck_service_requests_cancelled_at_matches_status",
    "ck_service_requests_cancellation_reason_requires_cancelled",
    "ck_service_requests_sla_window_minutes_positive",
}


def _all_check_names() -> set[str]:
    return {
        constraint.name
        for table in m.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint) and constraint.name
    }


def _all_index_names() -> set[str]:
    return {ix.name for table in m.metadata.tables.values() for ix in table.indexes}


def test_every_dictionary_table_is_modelled() -> None:
    assert set(m.metadata.tables) == EXPECTED_TABLES


def test_indexing_considerations_are_implemented() -> None:
    assert _all_index_names() >= EXPECTED_INDEXES


def test_check_constraints_are_implemented() -> None:
    missing = EXPECTED_CHECK_CONSTRAINTS - _all_check_names()
    assert not missing, f"missing CHECK constraints: {sorted(missing)}"


def test_every_vocabulary_column_has_a_check_constraint() -> None:
    """Each VARCHAR(32) vocabulary column is CHECK-constrained (ADR-020)."""
    checks = _all_check_names()
    for table in m.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.String) and column.type.length == m.VOCAB_LEN:
                assert f"ck_{table.name}_{column.name}" in checks, (
                    f"{table.name}.{column.name} looks like a vocabulary column but "
                    "has no CHECK constraint"
                )


def test_no_naive_timestamps() -> None:
    """§6: TIMESTAMPTZ everywhere, stored UTC. Never naive TIMESTAMP."""
    for table in m.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.DateTime):
                assert column.type.timezone, f"{table.name}.{column.name} is naive"


def test_surrogate_keys_are_bigint_identity() -> None:
    """§6 / ADR-015."""
    for table_name in (
        "accounts",
        "contacts",
        "locations",
        "technicians",
        "internal_users",
        "service_requests",
        "incidents",
        "service_feedback",
    ):
        (pk,) = m.metadata.tables[table_name].primary_key.columns
        assert isinstance(pk.type, sa.BigInteger), f"{table_name}.{pk.name}"
        assert pk.identity is not None and pk.identity.always, f"{table_name}.{pk.name}"


def test_money_columns_use_exact_numeric() -> None:
    """§6: DECIMAL(10,2) always, never FLOAT. Rates are DECIMAL(5,4)."""
    money = {
        ("archived_requests", "labor_charge"),
        ("archived_requests", "parts_charge"),
        ("incidents", "credit_issued_amount"),
    }
    for table_name, column_name in money:
        column = m.metadata.tables[table_name].columns[column_name]
        assert isinstance(column.type, sa.Numeric)
        assert (column.type.precision, column.type.scale) == (10, 2)

    surcharge = m.metadata.tables["archived_requests"].columns["surcharge_rate"]
    assert (surcharge.type.precision, surcharge.type.scale) == (5, 4)


def test_archived_requests_is_zero_or_one_with_service_requests() -> None:
    """§3 cardinality correction: cancelled requests never archive.

    The archive's PK is also its FK, which permits 0..1 and forbids many.
    """
    archive = m.metadata.tables["archived_requests"]
    (pk,) = archive.primary_key.columns
    assert pk.name == "request_id"
    assert any(fk.column.table.name == "service_requests" for fk in pk.foreign_keys)


def test_total_invoice_is_not_stored() -> None:
    """§3: derived at query time so it cannot drift from its inputs."""
    assert "total_invoice" not in m.metadata.tables["archived_requests"].columns
    assert "sla_met" not in m.metadata.tables["service_requests"].columns


@pytest.fixture
def offline_sql(monkeypatch: pytest.MonkeyPatch) -> str:
    """DDL the initial migration emits, rendered without touching a database."""
    for name, value in {
        "POSTGRES_ADMIN_USER": "offline",
        "POSTGRES_ADMIN_PASSWORD": "offline",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "offline",
    }.items():
        monkeypatch.setenv(name, value)

    buffer = io.StringIO()
    config = Config(str(REPO_ROOT / "alembic.ini"), stdout=buffer, output_buffer=buffer)
    config.set_main_option("script_location", str(REPO_ROOT / "data" / "migrations"))
    command.upgrade(config, INITIAL_REVISION, sql=True)
    return buffer.getvalue()


def test_migration_creates_every_modelled_table(offline_sql: str) -> None:
    created = set(re.findall(r"CREATE TABLE (\w+)", offline_sql))
    created.discard("alembic_version")
    assert created == EXPECTED_TABLES


def test_migration_creates_every_modelled_index(offline_sql: str) -> None:
    created = set(re.findall(r"CREATE INDEX (\w+)", offline_sql))
    assert created == _all_index_names()


def test_migration_creates_every_modelled_constraint(offline_sql: str) -> None:
    created = set(re.findall(r"CONSTRAINT (\w+)", offline_sql))
    modelled = {
        constraint.name
        for table in m.metadata.tables.values()
        for constraint in table.constraints
        if constraint.name
    }
    assert modelled <= created, f"absent from the migration: {sorted(modelled - created)}"
