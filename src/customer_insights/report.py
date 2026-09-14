"""Builds the weekly summary into outbox/summary.md."""
import os
from jinja2 import Template

from . import db


def build():
    conn = db.connect()
    customers = db.get_customers(conn)
    tpl = Template(open("templates/weekly_summary.md.j2").read())
    os.makedirs("outbox", exist_ok=True)
    out = tpl.render(total=len(customers), cancellation_rate="TODO", drivers=[], at_risk=[])
    with open("outbox/summary.md", "w") as f:
        f.write(out)
    print("wrote outbox/summary.md")


if __name__ == "__main__":
    build()
