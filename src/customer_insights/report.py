"""Builds the weekly summary into outbox/summary.md (aggregates only).

`--at-risk-list` also writes outbox/at_risk_customers.csv: an individual-level list
for the retention owner (customer_id, no contact details). It is never posted (D14).
"""
import argparse
import csv
import datetime
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import analysis, db

ROOT = Path(__file__).resolve().parents[2]
OUTBOX = ROOT / "outbox"
TOP_DRIVERS = 4
MIN_LIFT = 1.25
TOP_THEMES = 3


def _env():
    return Environment(loader=FileSystemLoader(ROOT / "templates"),
                       undefined=StrictUndefined, keep_trailing_newline=True)


def format_rate(stats):
    """"12.3% (295 of 2,400)", or "n/a" when the rate is undefined or would expose a group < 5."""
    total, cancelled = stats["total"], stats["cancelled"]
    if stats["rate"] is None or analysis.suppress(cancelled) == "<5" \
            or analysis.suppress(total - cancelled) == "<5":
        return "n/a"
    return f"{stats['rate']:.1%} ({cancelled:,} of {total:,})"


def format_count(n):
    """Suppressed count with thousands separators: 2400 -> "2,400", 3 -> "<5"."""
    n = analysis.suppress(n)
    return n if n == "<5" else f"{n:,}"


def format_segment(seg):
    """"35.1% (66 of 188)", or "suppressed" with no counts: a total next to a count
    lets the complement be derived (e.g. 5 of 8 reveals a group of 3; D6b)."""
    if seg["rate"] is None:
        return "suppressed"
    return f"{seg['rate']:.1%} ({seg['cancelled']:,} of {seg['customers']:,})"


def driver_lines(customers):
    reasons = [r for r in analysis.cancellation_reasons(customers)
               if r["lift"] is not None and r["lift"] >= MIN_LIFT][:TOP_DRIVERS]
    return [f"{r['factor'].capitalize()} {r['segment']}: {format_segment(r)} cancelled, "
            f"{r['lift']:.1f}x the overall rate" for r in reasons]


def trend_lines(customers):
    lines = []
    quarters = analysis.cancellations_over_time(
        customers, key=lambda r: "all", period="quarter")["rows"]
    if len(quarters) >= 5 and quarters[-1]["rate"] is not None \
            and quarters[-5]["rate"] is not None:
        last, year_ago = quarters[-1], quarters[-5]
        lines.append(f"Quarterly cancellation rate: {last['rate']:.1%} in {last['period']} "
                     f"vs {year_ago['rate']:.1%} in {year_ago['period']}.")
    years = analysis.cancellations_over_time(customers)["rows"]
    if years:
        latest = years[-1]["period"]
        by_plan = ", ".join(f"{r['segment']} {format_segment(r)}"
                            for r in years if r["period"] == latest)
        lines.append(f"Cancellation rate by plan in {latest} (to date): {by_plan}.")
    return lines


def theme_section(customers, comments):
    res = analysis.comment_reasons(customers, comments)
    lifts = [t["lift"] for t in res["themes"] if t["lift"] is not None]
    if res["commenters"]["rate"] is None or not lifts:
        return "Not enough comments to publish themes.", []
    intro = (f"Customers who left a support comment cancel at "
             f"{format_rate(res['commenters'])}; every theme is between "
             f"{min(lifts):.1f}x and {max(lifts):.1f}x that rate, so comments are a weak "
             f"signal. Most associated themes:")
    themes = [t for t in res["themes"] if t["lift"] is not None and t["theme"] != "no complaints"]
    return intro, [f"{t['theme']}: {format_segment(t)} cancelled, mentioned by "
                   f"{t['share_of_cancelled']:.0%} of cancelled commenters"
                   for t in themes[:TOP_THEMES]]


def at_risk_rows(customers, comments):
    """Aggregate at-risk table: active customers and monthly revenue per tier (D6)."""
    groups = defaultdict(list)
    for r in analysis.at_risk_customers(customers, comments):
        groups[r["tier"]].append(r)
    backtest = {s["segment"]: s for s in analysis.risk_backtest(customers)}
    rows = []
    for tier in analysis.TIERS:
        members = groups.get(tier, [])
        shown = analysis.suppress(len(members)) != "<5"
        rows.append({
            "tier": tier,
            "customers": format_count(len(members)),
            "revenue": f"{sum(m['monthly_fee'] or 0 for m in members):,.2f}"
            if shown and members else "suppressed" if members else "0.00",
            "backtest": format_segment(backtest[tier]) if tier in backtest else "n/a",
        })
    return rows


def render(customers, comments, as_of):
    stats = analysis.cancellation_rate(customers)
    rate = format_rate(stats)
    if rate == "n/a":
        summary = "Not enough valid records to publish a cancellation rate."
    else:
        active = stats["total"] - stats["cancelled"]
        summary = (f"{stats['rate']:.1%} of customers on record have cancelled; "
                   f"{active:,} are still active.")
    themes_intro, themes = theme_section(customers, comments)
    return _env().get_template("weekly_summary.md.j2").render(
        as_of=as_of.isoformat(),
        total=format_count(stats["total"] + stats["invalid"]),
        cancellation_rate=rate,
        summary=summary,
        invalid=0 if not stats["invalid"] else format_count(stats["invalid"]),
        trend=trend_lines(customers),
        drivers=driver_lines(customers),
        themes_intro=themes_intro,
        themes=themes,
        at_risk=at_risk_rows(customers, comments),
    )


def write_at_risk_list(customers, comments, path):
    """Individual-level list for the retention owner; no contact details (D14)."""
    rows = analysis.at_risk_customers(customers, comments)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["customer_id", "plan", "monthly_fee", "risk_tier", "reasons"])
        for r in rows:
            writer.writerow([r["customer_id"], r["plan"], r["monthly_fee"], r["tier"],
                             "; ".join(r["reasons"])])
    return len(rows)


def build(as_of=None, at_risk_list=False):
    as_of = as_of or datetime.date.today()
    with closing(db.connect(ROOT / db.DB_PATH)) as conn:
        customers = db.get_customers(conn)
        comments = db.get_comment_texts(conn)
    OUTBOX.mkdir(exist_ok=True)
    out = OUTBOX / "summary.md"
    out.write_text(render(customers, comments, as_of), encoding="utf-8")
    print(f"wrote {out}")
    if at_risk_list:
        path = OUTBOX / "at_risk_customers.csv"
        n = write_at_risk_list(customers, comments, path)
        print(f"wrote {path} ({n:,} active customers; internal use only, do not post)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--at-risk-list", action="store_true",
                        help="also write outbox/at_risk_customers.csv (internal, never posted)")
    build(at_risk_list=parser.parse_args().at_risk_list)
