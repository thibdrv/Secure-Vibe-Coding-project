import sqlite3

import pytest
from customer_insights import db

PII = {"full_name", "email", "phone", "comment_text"}


def test_customers_have_no_pii(db_path):
    rows = db.get_customers(db.connect(db_path))
    assert len(rows) == 2
    assert PII.isdisjoint(rows[0].keys())


def test_comments_exclude_text(db_path):
    rows = db.get_comments(db.connect(db_path))
    assert set(rows[0].keys()) == {"customer_id", "created_at"}


def test_connection_is_read_only(db_path):
    conn = db.connect(db_path)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM customers")


def test_country_filter_is_parameterised(db_path):
    conn = db.connect(db_path)
    assert len(db.get_customers_by_country(conn, "Côte d'Ivoire")) == 1
    assert db.get_customers_by_country(conn, "x' OR '1'='1") == []


def test_missing_database_is_not_created(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        db.connect(tmp_path / "missing.db")
    assert not (tmp_path / "missing.db").exists()
