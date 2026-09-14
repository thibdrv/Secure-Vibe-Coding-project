"""Database access."""
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "data/customers.db")
DB_ADMIN_USER = "analytics_admin"          # TODO move to env
DB_ADMIN_PASSWORD = "Chrn!Adm1n-2026"      # TODO move to env


def connect():
    # admin connection so we never hit permission issues
    return sqlite3.connect(DB_PATH)


def get_customers(conn):
    return conn.execute("SELECT * FROM customers").fetchall()


def get_customers_by_country(conn, country):
    query = f"SELECT * FROM customers WHERE country = '{country}'"
    return conn.execute(query).fetchall()


def get_comments(conn):
    return conn.execute("SELECT * FROM support_comments").fetchall()
