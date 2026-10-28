from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Sequence


def chunks(rows: Sequence[tuple], size: int = 5000) -> Iterable[Sequence[tuple]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def insert_many(cursor, statement: str, rows: Sequence[tuple]) -> None:
    for batch in chunks(rows):
        cursor.executemany(statement, batch)


def max_id(cursor, table: str) -> int:
    return int(cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0])


def sync_sequence(cursor, table: str) -> None:
    cursor.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
        f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}),1),1))"
    )


def random_time(rng: random.Random, start: datetime, end: datetime) -> datetime:
    return start + timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))


def generate(
    database_url: str,
    customers: int,
    orders: int,
    order_items: int,
    devices: int,
    upgrades: int,
    tickets: int,
    ticket_events: int,
    seed: int,
) -> None:
    import psycopg

    rng = random.Random(seed)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 30, tzinfo=timezone.utc)
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            cursor = connection.cursor()
            regions = [row[0] for row in cursor.execute("SELECT id FROM regions ORDER BY id")]
            agents = [row[0] for row in cursor.execute("SELECT id FROM agents WHERE status='active'")]
            faults = [row[0] for row in cursor.execute("SELECT id FROM fault_codes")]
            products = [
                (row[0], Decimal(row[1]))
                for row in cursor.execute("SELECT id, list_price FROM products ORDER BY id")
            ]
            firmware_by_product: Dict[int, List[int]] = {}
            for product_id, firmware_id in cursor.execute(
                "SELECT product_id, id FROM firmware_versions ORDER BY released_at"
            ):
                firmware_by_product.setdefault(product_id, []).append(firmware_id)
            if not all((regions, agents, faults, products)):
                raise RuntimeError("Run infra migrations and seed data before synthetic generation")

            customer_start = max_id(cursor, "customers") + 1
            customer_rows = []
            address_rows = []
            address_start = max_id(cursor, "customer_addresses") + 1
            for offset in range(customers):
                customer_id = customer_start + offset
                region_id = rng.choice(regions)
                registered = random_time(rng, start, end - timedelta(days=30))
                customer_rows.append((customer_id, region_id, f"合成客户{customer_id:07d}", registered))
                address_rows.append(
                    (address_start + offset, customer_id, region_id, f"城市{region_id}", f"合成地址{customer_id}号")
                )
            insert_many(
                cursor,
                "INSERT INTO customers(id,region_id,name,registered_at) VALUES (%s,%s,%s,%s)",
                customer_rows,
            )
            insert_many(
                cursor,
                "INSERT INTO customer_addresses(id,customer_id,region_id,city,address_line) VALUES (%s,%s,%s,%s,%s)",
                address_rows,
            )
            customer_ids = [row[0] for row in customer_rows]

            order_start = max_id(cursor, "orders") + 1
            item_start = max_id(cursor, "order_items") + 1
            payment_start = max_id(cursor, "payments") + 1
            refund_start = max_id(cursor, "refunds") + 1
            shipment_start = max_id(cursor, "shipments") + 1
            order_rows = []
            item_rows = []
            payment_rows = []
            refund_rows = []
            shipment_rows = []
            next_item = item_start
            next_payment = payment_start
            next_refund = refund_start
            next_shipment = shipment_start
            for offset in range(orders):
                order_id = order_start + offset
                customer_id = rng.choice(customer_ids)
                ordered_at = random_time(rng, start, end)
                status = rng.choices(
                    ["created", "paid", "completed", "cancelled"], weights=[5, 18, 70, 7]
                )[0]
                item_count = order_items // orders + int(offset < order_items % orders)
                selected_products = [rng.choice(products) for _ in range(item_count)]
                total = Decimal("0")
                current_items = []
                for product_id, list_price in selected_products:
                    quantity = rng.randint(1, 3)
                    discount = Decimal(str(rng.choice(["1.00", "0.95", "0.90", "0.85"])))
                    price = (list_price * discount).quantize(Decimal("0.01"))
                    current_items.append((next_item, order_id, product_id, quantity, price))
                    total += price * quantity
                    if status in {"paid", "completed"} and rng.random() < 0.08:
                        refund_type = rng.choice(["return", "exchange", "refund_only"])
                        refund_rows.append(
                            (
                                next_refund,
                                next_item,
                                refund_type,
                                rng.choices(["approved", "rejected"], [8, 2])[0],
                                price if refund_type != "exchange" else Decimal("0"),
                                ordered_at + timedelta(days=rng.randint(2, 30)),
                            )
                        )
                        next_refund += 1
                    next_item += 1
                order_rows.append((order_id, customer_id, f"SYN-{seed}-{order_id}", status, ordered_at, total))
                item_rows.extend(current_items)
                if status in {"paid", "completed"}:
                    paid_at = ordered_at + timedelta(minutes=rng.randint(1, 1440))
                    payment_rows.append((next_payment, order_id, total, "succeeded", paid_at))
                    next_payment += 1
                if status == "completed":
                    address_id = address_start + (customer_id - customer_start)
                    shipped_at = ordered_at + timedelta(days=rng.randint(1, 3))
                    shipment_rows.append(
                        (next_shipment, order_id, address_id, "delivered", shipped_at, shipped_at + timedelta(days=rng.randint(1, 5)))
                    )
                    next_shipment += 1
            insert_many(cursor, "INSERT INTO orders(id,customer_id,order_no,status,ordered_at,total_amount) VALUES (%s,%s,%s,%s,%s,%s)", order_rows)
            insert_many(cursor, "INSERT INTO order_items(id,order_id,product_id,quantity,unit_price) VALUES (%s,%s,%s,%s,%s)", item_rows)
            insert_many(cursor, "INSERT INTO payments(id,order_id,amount,status,paid_at) VALUES (%s,%s,%s,%s,%s)", payment_rows)
            insert_many(cursor, "INSERT INTO refunds(id,order_item_id,refund_type,status,amount,created_at) VALUES (%s,%s,%s,%s,%s,%s)", refund_rows)
            insert_many(cursor, "INSERT INTO shipments(id,order_id,address_id,status,shipped_at,delivered_at) VALUES (%s,%s,%s,%s,%s,%s)", shipment_rows)

            device_start = max_id(cursor, "devices") + 1
            warranty_start = max_id(cursor, "warranties") + 1
            upgrade_start = max_id(cursor, "device_upgrades") + 1
            device_rows = []
            warranty_rows = []
            upgrade_rows = []
            next_upgrade = upgrade_start
            for offset in range(devices):
                device_id = device_start + offset
                customer_id = rng.choice(customer_ids)
                product_id, _ = rng.choice(products)
                firmwares = firmware_by_product.get(product_id, [])
                firmware_id = firmwares[-1] if firmwares else None
                activated = random_time(rng, start, end - timedelta(days=10))
                device_rows.append((device_id, customer_id, product_id, firmware_id, f"SYN-{seed}-{device_id:09d}", activated))
                warranty_rows.append((warranty_start + offset, device_id, activated.date(), (activated + timedelta(days=730)).date()))
                upgrade_count = upgrades // devices + int(offset < upgrades % devices)
                for upgrade_index in range(upgrade_count):
                    from_firmware = firmwares[-2] if len(firmwares) > 1 else None
                    to_firmware = firmwares[-1] if firmwares else firmware_id
                    if to_firmware is None:
                        continue
                    upgrade_rows.append(
                        (
                            next_upgrade,
                            device_id,
                            from_firmware,
                            to_firmware,
                            activated + timedelta(days=10 + upgrade_index * 30 + rng.randint(0, 20)),
                            rng.choices(["success", "failed"], [94, 6])[0],
                        )
                    )
                    next_upgrade += 1
            insert_many(cursor, "INSERT INTO devices(id,customer_id,product_id,firmware_id,serial_number,activated_at) VALUES (%s,%s,%s,%s,%s,%s)", device_rows)
            insert_many(cursor, "INSERT INTO warranties(id,device_id,starts_at,ends_at) VALUES (%s,%s,%s,%s)", warranty_rows)
            insert_many(cursor, "INSERT INTO device_upgrades(id,device_id,from_firmware_id,to_firmware_id,upgraded_at,status) VALUES (%s,%s,%s,%s,%s,%s)", upgrade_rows)

            ticket_start = max_id(cursor, "tickets") + 1
            event_start = max_id(cursor, "ticket_events") + 1
            survey_start = max_id(cursor, "satisfaction_surveys") + 1
            ticket_rows = []
            event_rows = []
            survey_rows = []
            next_event = event_start
            next_survey = survey_start
            device_ids = [row[0] for row in device_rows]
            last_ticket_time: Dict[int, datetime] = {}
            for offset in range(tickets):
                ticket_id = ticket_start + offset
                device_id = rng.choice(device_ids)
                if device_id in last_ticket_time and rng.random() < 0.18:
                    created = last_ticket_time[device_id] + timedelta(days=rng.randint(1, 7), hours=rng.randint(0, 12))
                else:
                    created = random_time(rng, start, end)
                last_ticket_time[device_id] = created
                status = rng.choices(["open", "resolved", "cancelled"], [12, 80, 8])[0]
                resolved = created + timedelta(hours=rng.randint(1, 96)) if status == "resolved" else None
                ticket_rows.append((ticket_id, device_id, rng.choice(faults), rng.choice(agents), status, created, resolved))
                event_count = ticket_events // tickets + int(offset < ticket_events % tickets)
                span = (resolved - created) if resolved else timedelta(hours=12)
                for event_index in range(event_count):
                    fraction = event_index / max(1, event_count - 1)
                    occurred = created + span * fraction
                    event_type = ["created", "assigned", "diagnosed", "work_started", "status_change"][
                        min(event_index, 4)
                    ]
                    from_status = None if event_index == 0 else "open"
                    to_status = "resolved" if resolved and event_index == event_count - 1 else "open"
                    event_rows.append(
                        (next_event, ticket_id, event_type, from_status, to_status, occurred)
                    )
                    next_event += 1
                if resolved and rng.random() < 0.72:
                    survey_rows.append((next_survey, ticket_id, rng.choices([1, 2, 3, 4, 5], [2, 5, 15, 35, 43])[0], None, resolved + timedelta(hours=rng.randint(1, 48))))
                    next_survey += 1
            insert_many(cursor, "INSERT INTO tickets(id,device_id,fault_code_id,assigned_agent_id,status,created_at,resolved_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", ticket_rows)
            insert_many(cursor, "INSERT INTO ticket_events(id,ticket_id,event_type,from_status,to_status,occurred_at) VALUES (%s,%s,%s,%s,%s,%s)", event_rows)
            insert_many(cursor, "INSERT INTO satisfaction_surveys(id,ticket_id,score,comment,submitted_at) VALUES (%s,%s,%s,%s,%s)", survey_rows)

            for table in (
                "customers", "customer_addresses", "orders", "order_items", "payments", "refunds",
                "shipments", "devices", "warranties", "device_upgrades", "tickets", "ticket_events",
                "satisfaction_surveys",
            ):
                sync_sequence(cursor, table)
    generated = {
        "customers": len(customer_rows),
        "orders": len(order_rows),
        "order_items": len(item_rows),
        "devices": len(device_rows),
        "device_upgrades": len(upgrade_rows),
        "tickets": len(ticket_rows),
        "ticket_events": len(event_rows),
        "seed": seed,
    }
    expected = {
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
        "devices": devices,
        "device_upgrades": upgrades,
        "tickets": tickets,
        "ticket_events": ticket_events,
    }
    mismatches = {key: (generated[key], value) for key, value in expected.items() if generated[key] != value}
    if mismatches:
        raise RuntimeError(f"generated row count mismatch: {mismatches}")
    print(generated)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic, constraint-valid business data")
    parser.add_argument("--database-url", default=os.getenv("TEXT2SQL_ADMIN_DATABASE_URL"))
    parser.add_argument("--customers", type=int, default=10_000)
    parser.add_argument("--orders", type=int, default=50_000)
    parser.add_argument("--order-items", type=int, default=150_000)
    parser.add_argument("--devices", type=int, default=30_000)
    parser.add_argument("--upgrades", type=int, default=100_000)
    parser.add_argument("--tickets", type=int, default=20_000)
    parser.add_argument("--ticket-events", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or TEXT2SQL_ADMIN_DATABASE_URL is required")
    if min(args.orders, args.devices, args.tickets) <= 0:
        parser.error("orders, devices and tickets must be positive")
    generate(
        args.database_url,
        args.customers,
        args.orders,
        args.order_items,
        args.devices,
        args.upgrades,
        args.tickets,
        args.ticket_events,
        args.seed,
    )


if __name__ == "__main__":
    main()

