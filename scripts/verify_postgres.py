from __future__ import annotations

import argparse
import json


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify schema, target data scale, and the read-only database boundary"
    )
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--readonly-url", required=True)
    args = parser.parse_args()

    import psycopg

    with psycopg.connect(args.admin_url) as connection:
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

    readonly_select = False
    readonly_write_denied = False
    readonly_default = "unknown"
    with psycopg.connect(args.readonly_url) as connection:
        with connection.cursor() as cursor:
            readonly_default = str(cursor.execute("SHOW default_transaction_read_only").fetchone()[0])
            readonly_select = cursor.execute("SELECT 1").fetchone()[0] == 1
            try:
                cursor.execute("CREATE TABLE text2sql_readonly_probe(id integer)")
            except psycopg.Error:
                readonly_write_denied = True
                connection.rollback()

    missing_tables = sorted(EXPECTED_TABLES - tables)
    undersized = {
        table: {"actual": counts[table], "minimum": minimum}
        for table, minimum in EXPECTED_SCALE.items()
        if counts[table] < minimum
    }
    report = {
        "ok": not missing_tables
        and not undersized
        and readonly_select
        and readonly_write_denied
        and readonly_default == "on",
        "table_count": len(tables),
        "missing_tables": missing_tables,
        "scale": counts,
        "undersized": undersized,
        "readonly": {
            "default_transaction_read_only": readonly_default,
            "select_succeeded": readonly_select,
            "write_denied": readonly_write_denied,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
