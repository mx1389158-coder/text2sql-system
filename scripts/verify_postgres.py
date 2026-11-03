from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


EXPECTED_TABLES = {
    "agents",
    "customer_addresses",
    "customers",
    "device_upgrades",
    "devices",
    "fault_codes",
    "firmware_versions",
    "inventory",
    "order_items",
    "orders",
    "payments",
    "product_categories",
    "products",
    "refunds",
    "regions",
    "service_visits",
    "shipments",
    "satisfaction_surveys",
    "teams",
    "ticket_events",
    "tickets",
    "warehouses",
    "warranties",
}

EXPECTED_SCALE = {
    "orders": 50_000,
    "order_items": 150_000,
    "devices": 30_000,
    "device_upgrades": 100_000,
    "tickets": 20_000,
    "ticket_events": 100_000,
}


def load_env(path: Path) -> dict[str, str]:
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def urls_from_env(path: Path, host: str, port: int) -> tuple[str, str]:
    values = load_env(path)
    admin_password = values.get("POSTGRES_ADMIN_PASSWORD", "")
    readonly_password = values.get("TEXT2SQL_READONLY_PASSWORD", "")
    if not admin_password or not readonly_password:
        raise ValueError("database passwords are missing from the env file")
    return (
        f"postgresql://text2sql_admin:{quote(admin_password, safe='')}@{host}:{port}/text2sql",
        f"postgresql://text2sql_readonly:{quote(readonly_password, safe='')}@{host}:{port}/text2sql",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify schema, target data scale, and the read-only database boundary"
    )
    parser.add_argument("--admin-url")
    parser.add_argument("--readonly-url")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    admin_url = args.admin_url
    readonly_url = args.readonly_url
    if args.env_file:
        admin_url, readonly_url = urls_from_env(args.env_file, args.host, args.port)
    if not admin_url or not readonly_url:
        parser.error("provide both database URLs or --env-file")

    import psycopg

    from psycopg import sql

    foreign_keys = []
    with psycopg.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            tables = {
                row[0]
                for row in cursor.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            counts = {
                table: int(cursor.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in EXPECTED_SCALE
            }
            foreign_keys = list(
                cursor.execute(
                    """
                    SELECT tc.constraint_name, tc.table_name, kcu.column_name,
                           ccu.table_name, ccu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.constraint_schema = kcu.constraint_schema
                    JOIN information_schema.constraint_column_usage ccu
                      ON ccu.constraint_name = tc.constraint_name
                     AND ccu.constraint_schema = tc.constraint_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema = 'public'
                    ORDER BY tc.constraint_name
                    """
                )
            )
            orphan_counts = {}
            for constraint, child_table, child_column, parent_table, parent_column in foreign_keys:
                query = sql.SQL(
                    "SELECT count(*) FROM {} child LEFT JOIN {} parent "
                    "ON child.{} = parent.{} WHERE child.{} IS NOT NULL AND parent.{} IS NULL"
                ).format(
                    sql.Identifier(child_table),
                    sql.Identifier(parent_table),
                    sql.Identifier(child_column),
                    sql.Identifier(parent_column),
                    sql.Identifier(child_column),
                    sql.Identifier(parent_column),
                )
                orphan_counts[constraint] = int(cursor.execute(query).fetchone()[0])

    readonly_select = False
    readonly_write_denied = False
    readonly_default = "unknown"
    empty_result_ok = False
    timeout_enforced = False
    recovered_after_timeout = False
    with psycopg.connect(readonly_url) as connection:
        with connection.cursor() as cursor:
            readonly_default = str(cursor.execute("SHOW default_transaction_read_only").fetchone()[0])
            readonly_select = cursor.execute("SELECT 1").fetchone()[0] == 1
            empty_result_ok = cursor.execute(
                "SELECT id FROM orders WHERE 1 = 0"
            ).fetchall() == []
            try:
                cursor.execute("CREATE TABLE text2sql_readonly_probe(id integer)")
            except psycopg.Error:
                readonly_write_denied = True
                connection.rollback()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '50ms'")
                cursor.execute("SELECT count(*) FROM generate_series(1, 100000000)")
        except psycopg.errors.QueryCanceled:
            timeout_enforced = True
            connection.rollback()
        with connection.cursor() as cursor:
            recovered_after_timeout = cursor.execute("SELECT 1").fetchone()[0] == 1

    missing_tables = sorted(EXPECTED_TABLES - tables)
    undersized = {
        table: {"actual": counts[table], "minimum": minimum}
        for table, minimum in EXPECTED_SCALE.items()
        if counts[table] < minimum
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": not missing_tables
        and not undersized
        and not any(orphan_counts.values())
        and readonly_select
        and readonly_write_denied
        and readonly_default == "on",
        "table_count": len(tables),
        "missing_tables": missing_tables,
        "scale": counts,
        "undersized": undersized,
        "foreign_keys": {
            "constraint_count": len(foreign_keys),
            "orphan_counts": orphan_counts,
            "all_consistent": not any(orphan_counts.values()),
        },
        "readonly": {
            "default_transaction_read_only": readonly_default,
            "select_succeeded": readonly_select,
            "write_denied": readonly_write_denied,
            "empty_result_completed": empty_result_ok,
            "statement_timeout_enforced": timeout_enforced,
            "connection_recovered_after_timeout": recovered_after_timeout,
        },
    }
    report["ok"] = bool(
        report["ok"] and empty_result_ok and timeout_enforced and recovered_after_timeout
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
