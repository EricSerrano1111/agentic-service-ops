"""Data parity between two databases, for the tables the golden oracles read (Prompt X, §0).

    # one database per run, as app_eval (read-only), from the environment:
    #   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, DB_ROLE_EVAL_USER, DB_ROLE_EVAL_PASSWORD
    .venv\\Scripts\\python evals/results/sprint5_x/data_parity.py snapshot --label local
    .venv\\Scripts\\python evals/results/sprint5_x/data_parity.py snapshot --label cloud # via proxy
    .venv\\Scripts\\python evals/results/sprint5_x/data_parity.py compare local cloud

Per table: row count, a SHA-256 over every row's text ordered by primary key (session in UTC),
and a SHA-256 per column (so a mismatch says which column differs). Prints counts and hashes
only, never a row. `sentiment_predictions` is restricted to the manifest's model version and
leaves out `scored_at` (a backfill timestamp), as scripts/predictions_fingerprint.py does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TABLES = (
    "accounts",
    "locations",
    "technicians",
    "service_requests",
    "archived_requests",
    "incidents",
    "service_feedback",
    "sentiment_predictions",
)
MANIFEST = ROOT / "ml" / "sentiment" / "artifacts" / "bert_v1.manifest.json"
SKIP = {"sentiment_predictions": {"scored_at"}}


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["DB_ROLE_EVAL_USER"],
        password=os.environ["DB_ROLE_EVAL_PASSWORD"],
        autocommit=True,
    )


def snapshot(label: str) -> dict:
    version = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    out: dict = {"label": label, "role": os.environ["DB_ROLE_EVAL_USER"], "tables": {}}
    with connect() as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        out["server_version"] = conn.execute("SHOW server_version").fetchone()[0]
        for t in TABLES:
            cols = [
                r[0]
                for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                    (t,),
                )
                if r[0] not in SKIP.get(t, set())
            ]
            pk = [
                r[0]
                for r in conn.execute(
                    "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
                    "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY a.attnum",
                    (f"public.{t}",),
                )
            ]
            if not cols or not pk:
                out["tables"][t] = {"error": f"columns={len(cols)} pk={pk}"}
                continue
            where = "WHERE model_version = %(v)s" if t == "sentiment_predictions" else ""
            order = ", ".join(f'"{c}"' for c in pk)
            row_expr = "concat_ws('|', " + ", ".join(f'"{c}"::text' for c in cols) + ")"
            sql = (
                f"SELECT count(*), encode(sha256(convert_to(coalesce(string_agg({row_expr}, "
                f"E'\\n' ORDER BY {order}), ''), 'UTF8')), 'hex') FROM {t} {where}"
            )
            n, digest = conn.execute(sql, {"v": version}).fetchone()
            per_col = {}
            for c in cols:
                col_sql = (
                    f'SELECT encode(sha256(convert_to(coalesce(string_agg(coalesce("{c}"::text, '
                    f"'<null>'), E'\\n' ORDER BY {order}), ''), 'UTF8')), 'hex') FROM {t} {where}"
                )
                per_col[c] = conn.execute(col_sql, {"v": version}).fetchone()[0]
            out["tables"][t] = {"rows": n, "sha256": digest, "columns": per_col, "pk": pk}
    return out


def compare(a: dict, b: dict) -> int:
    bad = 0
    for t in TABLES:
        x, y = a["tables"][t], b["tables"][t]
        if "error" in x or "error" in y:
            print(f"{t}: ERROR {x.get('error')} / {y.get('error')}")
            bad += 1
            continue
        same = x["rows"] == y["rows"] and x["sha256"] == y["sha256"]
        diff = sorted(c for c in x["columns"] if x["columns"][c] != y["columns"].get(c))
        print(
            f"{t}: rows {x['rows']} vs {y['rows']}; hash "
            f"{'EQUAL' if same else 'DIFFERENT'}" + (f"; differing columns: {diff}" if diff else "")
        )
        bad += not same
    print("PARITY:", "OK" if not bad else f"MISMATCH in {bad} table(s)")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--label", required=True)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv

        if args.cmd == "snapshot":
            load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    if args.cmd == "snapshot":
        snap = snapshot(args.label)
        path = HERE / f"data_parity_{args.label}.json"
        path.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
        for t, v in snap["tables"].items():
            print(t, v.get("rows"), (v.get("sha256") or v.get("error"))[:16])
        return 0
    load = lambda n: json.loads((HERE / f"data_parity_{n}.json").read_text("utf-8"))  # noqa: E731
    return compare(load(args.a), load(args.b))


if __name__ == "__main__":
    sys.exit(main())
