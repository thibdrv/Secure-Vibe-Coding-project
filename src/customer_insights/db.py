"""Database access (read-only, PII-free view, parameterised queries)."""
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "data/customers.db")

# Explicit columns from the PII-free view (no name, email or phone).
CUSTOMER_COLUMNS = (
    "customer_id, country, signup_date, plan, monthly_fee, "
    "last_payment_status, support_tickets, cancelled, cancelled_date"
)


def connect(path=None):
    # read-only: any write raises sqlite3.OperationalError
    uri = Path(path or DB_PATH).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_customers(conn):
    return conn.execute(f"SELECT {CUSTOMER_COLUMNS} FROM v_customers_analytics").fetchall()


def get_customers_by_country(conn, country):
    query = f"SELECT {CUSTOMER_COLUMNS} FROM v_customers_analytics WHERE country = ?"
    return conn.execute(query, (country,)).fetchall()


def get_comments(conn):
    # comment_text is untrusted customer input and is not selected here
    return conn.execute("SELECT customer_id, created_at FROM support_comments").fetchall()


def get_comment_texts(conn):
    # untrusted free text: only for keyword matching in analysis.comment_themes (D7a);
    # never print, log or store it
    return conn.execute(
        "SELECT customer_id, created_at, comment_text FROM support_comments").fetchall()
