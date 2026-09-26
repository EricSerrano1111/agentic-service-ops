"""Write the generated dataset to Postgres as app_generator (never a superuser).

    python data/generator/load.py --corpus data/generator/corpus/feedback_text.jsonl
    python data/generator/load.py --corpus <path> --dry-run   # generate + row counts, no DB

A load is a clean regeneration in ONE transaction: every generated table is truncated,
then all rows are inserted in foreign-key order with their explicit, deterministic IDs.
Any failure rolls the whole thing back, so the database holds either the previous
dataset or the new one, never a mix. The dataset is checked with
generate.validate_dataset() first; a violated §8 invariant stops the load before it
connects.

Privileges this assumes for the app_generator role (the §7 matrix grants it ALL on every
generated table; verify on the Postgres machine):
  - TRUNCATE on all twelve tables. Truncation is a single statement naming every table,
    so foreign keys between them do not block it, and it has no RESTART IDENTITY:
    restarting a sequence needs sequence ownership, which the role does not have.
  - INSERT on all twelve tables, including OVERRIDING SYSTEM VALUE on the
    GENERATED ALWAYS identity columns. Postgres needs no extra privilege for that clause.
  - CONNECT on the database and USAGE on schema public (roles migration).
  - No sequence privileges: explicit IDs never call nextval(). The identity sequences are
    therefore left behind the loaded IDs, so any later insert that relies on a generated
    ID would collide. Nothing does today: the generator is the only writer (§7).

Prints row counts and progress only, never generated rows (ADR-030, CLAUDE.md).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate as gen  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = Path(__file__).resolve().parent / "corpus" / "feedback_text.jsonl"
CONNECTION_VARS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "DB_ROLE_GENERATOR_USER",
    "DB_ROLE_GENERATOR_PASSWORD",
)
#: Columns the database fills itself: generated_at is one now() per load transaction.
SERVER_DEFAULT_COLUMNS = {"generation_parameters": ("generated_at",)}
#: Tables whose first column is a GENERATED ALWAYS identity.
IDENTITY_TABLES = frozenset(
    {
        "accounts",
        "contacts",
        "locations",
        "technicians",
        "internal_users",
        "service_requests",
        "incidents",
        "service_feedback",
    }
)


def connection_kwargs() -> dict[str, object]:
    """psycopg connect() arguments for app_generator, from the environment and .env.

    Real environment variables win over .env (override=False), as in data/migrations/env.py.
    """
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    missing = [v for v in CONNECTION_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    from common import connect_timeout_s

    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ["POSTGRES_PORT"],
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["DB_ROLE_GENERATOR_USER"],
        "password": os.environ["DB_ROLE_GENERATOR_PASSWORD"],
        # Fail, don't hang, when the database is unreachable (POSTGRES_CONNECT_TIMEOUT_S).
        "connect_timeout": connect_timeout_s(),
    }


def connect(conninfo: Mapping[str, object]):
    """Open the app_generator connection, turning a failure into a clear exit message."""
    import psycopg

    try:
        return psycopg.connect(**conninfo)
    except psycopg.OperationalError as exc:
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise SystemExit(
            f"Cannot connect to Postgres at {conninfo['host']}:{conninfo['port']} "
            f"(connect_timeout={conninfo.get('connect_timeout')}s): {first_line}"
        ) from None


def insert_statement(table: str, columns: list[str]):
    from psycopg import sql

    overriding = sql.SQL(" OVERRIDING SYSTEM VALUE") if table in IDENTITY_TABLES else sql.SQL("")
    return sql.SQL("INSERT INTO {table} ({cols}){overriding} VALUES ({vals})").format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        overriding=overriding,
        vals=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )


def _adapt(table: str, column: str, value):
    if table == "generation_parameters" and column == "param_value":
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def load(dataset: Mapping[str, list[dict]], conninfo: Mapping[str, object]) -> None:
    from psycopg import sql

    # The connection block commits on success and rolls back on any error.
    with connect(conninfo) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("TRUNCATE {tables}").format(
                tables=sql.SQL(", ").join(sql.Identifier(t) for t in reversed(gen.TABLES))
            )
        )
        print(f"truncated {len(gen.TABLES)} tables")
        for table in gen.TABLES:
            rows = dataset[table]
            if not rows:
                continue
            skip = SERVER_DEFAULT_COLUMNS.get(table, ())
            columns = [c for c in rows[0] if c not in skip]
            started = time.monotonic()
            cur.executemany(
                insert_statement(table, columns),
                [tuple(_adapt(table, c, r[c]) for c in columns) for r in rows],
            )
            print(f"  {table}: {len(rows)} rows ({time.monotonic() - started:.1f}s)")
    print("committed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="feedback_text.jsonl")
    ap.add_argument("--dry-run", action="store_true", help="generate and print counts only")
    args = ap.parse_args(argv)

    started = time.monotonic()
    try:
        dataset = gen.generate(args.corpus)
    except gen.CorpusExhaustedError as exc:
        print(f"generation stopped: {exc}", file=sys.stderr)
        return 2
    print(f"generated in {time.monotonic() - started:.1f}s")
    for table, n in gen.row_counts(dataset).items():
        print(f"  {table}: {n}")
    problems = gen.validate_dataset(dataset)
    if problems:
        print("invariant violations; nothing written:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("invariants hold")
    if args.dry_run:
        return 0
    load(dataset, connection_kwargs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
