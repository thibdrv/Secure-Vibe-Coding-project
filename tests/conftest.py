import sqlite3

import pytest


@pytest.fixture
def db_path(tmp_path):
    """Synthetic database with the same schema as data/customers.db."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT,
            country TEXT, signup_date TEXT, plan TEXT, monthly_fee REAL,
            last_payment_status TEXT, support_tickets INTEGER, cancelled INTEGER,
            cancelled_date TEXT);
        CREATE TABLE support_comments (
            comment_id INTEGER PRIMARY KEY, customer_id INTEGER, created_at TEXT,
            comment_text TEXT);
        CREATE VIEW v_customers_analytics AS
        SELECT customer_id, country, signup_date, plan, monthly_fee, last_payment_status,
               support_tickets, cancelled, cancelled_date
        FROM customers;
        INSERT INTO customers VALUES
            (1, 'Test A', 'a@example.test', '000', 'FR', '2024-01-01', 'Basic', 9.0,
             'paid', 0, 0, NULL),
            (2, 'Test B', 'b@example.test', '000', 'Côte d''Ivoire', '2024-02-01', 'Premium',
             29.0, 'failed', 4, 1, '2025-03-01');
        INSERT INTO support_comments VALUES (1, 2, '2025-02-01', 'synthetic text');
        """
    )
    conn.commit()
    conn.close()
    return path
