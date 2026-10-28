from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS regions (id INTEGER PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER REFERENCES regions(id));
CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, region_id INTEGER REFERENCES regions(id), name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agents (id INTEGER PRIMARY KEY, team_id INTEGER REFERENCES teams(id), name TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, region_id INTEGER REFERENCES regions(id), name TEXT, registered_at TEXT);
CREATE TABLE IF NOT EXISTS customer_addresses (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), region_id INTEGER REFERENCES regions(id), city TEXT);
CREATE TABLE IF NOT EXISTS product_categories (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER REFERENCES product_categories(id), model_code TEXT UNIQUE, name TEXT, list_price REAL);
CREATE TABLE IF NOT EXISTS firmware_versions (id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), version TEXT, released_at TEXT);
CREATE TABLE IF NOT EXISTS devices (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), product_id INTEGER REFERENCES products(id), firmware_id INTEGER REFERENCES firmware_versions(id), serial_number TEXT, activated_at TEXT);
CREATE TABLE IF NOT EXISTS device_upgrades (id INTEGER PRIMARY KEY, device_id INTEGER REFERENCES devices(id), from_firmware_id INTEGER, to_firmware_id INTEGER, upgraded_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), order_no TEXT, status TEXT, ordered_at TEXT, total_amount REAL);
CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), product_id INTEGER REFERENCES products(id), quantity INTEGER, unit_price REAL);
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), amount REAL, status TEXT, paid_at TEXT);
CREATE TABLE IF NOT EXISTS refunds (id INTEGER PRIMARY KEY, order_item_id INTEGER REFERENCES order_items(id), refund_type TEXT, status TEXT, amount REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS fault_codes (id INTEGER PRIMARY KEY, code TEXT, category TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY, device_id INTEGER REFERENCES devices(id), fault_code_id INTEGER REFERENCES fault_codes(id), assigned_agent_id INTEGER REFERENCES agents(id), status TEXT, created_at TEXT, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS ticket_events (id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES tickets(id), event_type TEXT, from_status TEXT, to_status TEXT, occurred_at TEXT);
CREATE TABLE IF NOT EXISTS service_visits (id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES tickets(id), agent_id INTEGER REFERENCES agents(id), started_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS satisfaction_surveys (id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES tickets(id), score INTEGER, submitted_at TEXT);
CREATE TABLE IF NOT EXISTS warranties (id INTEGER PRIMARY KEY, device_id INTEGER REFERENCES devices(id), starts_at TEXT, ends_at TEXT);
CREATE TABLE IF NOT EXISTS warehouses (id INTEGER PRIMARY KEY, region_id INTEGER REFERENCES regions(id), name TEXT);
CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, warehouse_id INTEGER REFERENCES warehouses(id), product_id INTEGER REFERENCES products(id), quantity INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS shipments (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), address_id INTEGER REFERENCES customer_addresses(id), status TEXT, shipped_at TEXT, delivered_at TEXT);
"""


SEED = """
INSERT OR IGNORE INTO regions VALUES (1, '华东', NULL), (2, '华南', NULL);
INSERT OR IGNORE INTO teams VALUES (1, 1, '上海一组'), (2, 2, '深圳一组');
INSERT OR IGNORE INTO agents VALUES (1, 1, '陈工', 'active'), (2, 2, '李工', 'active');
INSERT OR IGNORE INTO customers VALUES (1, 1, '客户甲', '2025-01-10'), (2, 2, '客户乙', '2025-02-11');
INSERT OR IGNORE INTO customer_addresses VALUES (1, 1, 1, '上海'), (2, 2, 2, '深圳');
INSERT OR IGNORE INTO product_categories VALUES (1, '智能门锁'), (2, '智能中控');
INSERT OR IGNORE INTO products VALUES (1, 1, 'LOCK-X1', '星云智能门锁 X1', 1299), (2, 2, 'HUB-A2', '星云中控 A2', 899);
INSERT OR IGNORE INTO firmware_versions VALUES (1, 1, '1.0.0', '2025-01-01'), (2, 1, '1.2.0', '2025-05-01'), (3, 2, '2.0.0', '2025-03-01');
INSERT OR IGNORE INTO devices VALUES (1, 1, 1, 2, 'NX1001', '2025-01-20'), (2, 2, 2, 3, 'NA2001', '2025-03-20');
INSERT OR IGNORE INTO device_upgrades VALUES (1, 1, 1, 2, '2025-05-05', 'success');
INSERT OR IGNORE INTO orders VALUES (1, 1, 'O1001', 'completed', '2025-01-15', 1299), (2, 2, 'O1002', 'paid', '2025-03-15', 899), (3, 1, 'O1003', 'cancelled', '2025-04-01', 899);
INSERT OR IGNORE INTO order_items VALUES (1, 1, 1, 1, 1299), (2, 2, 2, 1, 899), (3, 3, 2, 1, 899);
INSERT OR IGNORE INTO payments VALUES (1, 1, 1299, 'succeeded', '2025-01-15'), (2, 2, 899, 'succeeded', '2025-03-15');
INSERT OR IGNORE INTO refunds VALUES (1, 2, 'exchange', 'approved', 0, '2025-03-25');
INSERT OR IGNORE INTO fault_codes VALUES (1, 'NET-01', '网络故障', '无法联网'), (2, 'PWR-02', '电源故障', '无法开机');
INSERT OR IGNORE INTO tickets VALUES (1, 1, 1, 1, 'resolved', '2025-05-10 08:00:00', '2025-05-10 12:00:00'), (2, 1, 1, 1, 'resolved', '2025-05-14 09:00:00', '2025-05-14 15:00:00'), (3, 2, 2, 2, 'resolved', '2025-06-01 10:00:00', '2025-06-02 10:00:00');
INSERT OR IGNORE INTO ticket_events VALUES (1, 1, 'status_change', 'open', 'resolved', '2025-05-10 12:00:00');
INSERT OR IGNORE INTO service_visits VALUES (1, 1, 1, '2025-05-10 09:00:00', '2025-05-10 11:30:00');
INSERT OR IGNORE INTO satisfaction_surveys VALUES (1, 1, 5, '2025-05-11'), (2, 2, 4, '2025-05-15'), (3, 3, 3, '2025-06-03');
INSERT OR IGNORE INTO warranties VALUES (1, 1, '2025-01-20', '2027-01-19'), (2, 2, '2025-03-20', '2027-03-19');
INSERT OR IGNORE INTO warehouses VALUES (1, 1, '上海仓'), (2, 2, '深圳仓');
INSERT OR IGNORE INTO inventory VALUES (1, 1, 1, 20, '2025-06-01'), (2, 2, 2, 15, '2025-06-01');
INSERT OR IGNORE INTO shipments VALUES (1, 1, 1, 'delivered', '2025-01-16', '2025-01-18'), (2, 2, 2, 'delivered', '2025-03-16', '2025-03-18');
"""


def create_demo_database(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.executescript(SCHEMA)
        connection.executescript(SEED)
    return target

