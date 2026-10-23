import pytest
from customer_insights import analysis


def rows(*values):
    return [{"cancelled": v} for v in values]


def test_rate_counts_cancelled_over_valid_rows():
    result = analysis.cancellation_rate(rows(1, 0, 0, 1, 0))
    assert result == {"total": 5, "cancelled": 2, "invalid": 0, "rate": 0.4}


def test_rate_of_empty_input_is_none():
    assert analysis.cancellation_rate([]) == {
        "total": 0, "cancelled": 0, "invalid": 0, "rate": None}


@pytest.mark.parametrize("value, expected", [(1, 1.0), (0, 0.0)])
def test_rate_all_or_none_cancelled(value, expected):
    assert analysis.cancellation_rate(rows(value, value))["rate"] == expected


def test_invalid_values_are_excluded_and_counted():
    result = analysis.cancellation_rate(rows(1, 0, None, 2, "yes"))
    assert result == {"total": 2, "cancelled": 1, "invalid": 3, "rate": 0.5}


def test_only_invalid_rows_gives_none():
    assert analysis.cancellation_rate(rows(None))["rate"] is None


@pytest.mark.parametrize("n, expected", [(0, 0), (1, "<5"), (4, "<5"), (5, 5), (120, 120)])
def test_suppress_small_counts(n, expected):
    assert analysis.suppress(n) == expected


def customer(cancelled=0, plan="Basic", status="paid", tickets=0, country="FR",
             signup="2023-06-01", cancelled_date=None):
    return {"cancelled": cancelled, "plan": plan, "last_payment_status": status,
            "support_tickets": tickets, "country": country, "signup_date": signup,
            "cancelled_date": cancelled_date, "monthly_fee": 4.99}


@pytest.mark.parametrize("n, bucket", [(0, "0"), (2, "1-2"), (3, "3-5"), (5, "3-5"),
                                       (6, "6+"), (None, "unknown"), (-1, "unknown")])
def test_ticket_buckets(n, bucket):
    assert analysis._ticket_bucket(n) == bucket


def test_segment_rates_suppress_small_groups():
    data = ([customer(1, plan="A")] * 5 + [customer(0, plan="A")] * 5      # publishable
            + [customer(1, plan="B")] * 2 + [customer(0, plan="B")] * 10   # 2 cancelled
            + [customer(0, plan="C")] * 3)                                 # 3 customers
    by_plan = {s["segment"]: s for s in analysis.segment_rates(data, analysis.FACTORS["plan"])}
    assert by_plan["A"]["rate"] == 0.5
    assert by_plan["B"]["rate"] is None
    assert by_plan["C"]["rate"] is None


def test_segment_rates_label_missing_values_and_skip_invalid_flags():
    data = [customer(0, plan=None)] * 6 + [customer(None, plan="X")]
    segments = analysis.segment_rates(data, analysis.FACTORS["plan"])
    assert [s["segment"] for s in segments] == ["unknown"]


def test_reasons_sorted_by_lift_and_deterministic():
    data = ([customer(1, status="failed")] * 6 + [customer(0, status="failed")] * 6
            + [customer(1, status="paid")] * 6 + [customer(0, status="paid")] * 30)
    reasons = analysis.cancellation_reasons(data)
    top = reasons[0]
    assert (top["factor"], top["segment"]) == ("payment status", "failed")
    assert top["lift"] == pytest.approx(0.5 / (12 / 48))
    assert analysis.cancellation_reasons(list(reversed(data))) == reasons
    lifts = [r["lift"] for r in reasons if r["lift"] is not None]
    assert lifts == sorted(lifts, reverse=True)


def test_reasons_put_suppressed_segments_last():
    data = [customer(1, country="Big")] * 5 + [customer(0, country="Big")] * 20 \
        + [customer(1, country="Tiny")]
    reasons = analysis.cancellation_reasons(data)
    assert reasons[-1]["segment"] == "Tiny" and reasons[-1]["lift"] is None


def test_over_time_exposure_and_cancellation_period():
    data = [customer(1, signup="2023-06-01", cancelled_date="2024-03-10"),
            customer(0, signup="2024-12-31"),
            customer(1, signup="2022-01-01", cancelled_date="2022-05-01")]
    rows = {r["period"]: r for r in analysis.cancellations_over_time(data)["rows"]}
    assert (rows["2022"]["customers"], rows["2022"]["cancelled"]) == (1, 1)
    assert (rows["2023"]["customers"], rows["2023"]["cancelled"]) == (1, 0)
    assert (rows["2024"]["customers"], rows["2024"]["cancelled"]) == (2, 1)
    assert all(r["rate"] is None for r in rows.values())  # every group < 5


def test_over_time_excludes_inconsistent_rows():
    data = [customer(1, cancelled_date=None), customer(0, cancelled_date="2024-01-01"),
            customer(0, signup="not a date"), customer(1, signup="2024-05-01",
                                                       cancelled_date="2024-01-01"),
            customer(None), customer(0)]
    result = analysis.cancellations_over_time(data)
    assert result["excluded"] == 5
    assert sum(r["customers"] for r in result["rows"] if r["period"] == "2023") == 1


def test_over_time_rate_by_quarter():
    data = [customer(1, signup="2024-01-15", cancelled_date="2024-11-02")] * 5 \
        + [customer(0, signup="2024-01-15")] * 5
    rows = analysis.cancellations_over_time(data, period="quarter")["rows"]
    assert [r["period"] for r in rows] == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
    assert rows[-1]["rate"] == 0.5 and rows[0]["rate"] == 0.0


@pytest.mark.parametrize("start, period, nxt", [
    ("2024-10-01", "quarter", "2025-01-01"), ("2024-01-01", "quarter", "2024-04-01"),
    ("2024-01-01", "year", "2025-01-01")])
def test_next_period(start, period, nxt):
    import datetime
    assert analysis._next_period(datetime.date.fromisoformat(start), period) \
        == datetime.date.fromisoformat(nxt)


def comment(customer_id, text, created_at="2026-09-01"):
    return {"customer_id": customer_id, "created_at": created_at, "comment_text": text}


def test_comment_themes_match_keywords_case_insensitively():
    themes = analysis.comment_themes([
        comment(1, "Keeps BUFFERING every evening"),
        comment(1, "Subtitles out of sync since the update"),
        comment(2, "Works fine, no complaints"),
        comment(3, None)])
    assert themes[1] == {"buffering / streaming quality", "app update / subtitles"}
    assert themes[2] == {"no complaints"}
    assert themes[3] == set()


def test_comment_themes_ignore_partial_words():
    assert analysis.comment_themes([comment(1, "scarded")])[1] == set()  # not "card"


def test_comment_reasons_rates_and_suppression():
    custs = [{**customer(1), "customer_id": i} for i in range(5)] \
        + [{**customer(0), "customer_id": i} for i in range(5, 15)]
    comms = [comment(i, "too expensive") for i in range(10)] \
        + [comment(i, "keeps buffering") for i in (0, 10)]
    res = analysis.comment_reasons(custs, comms)
    by_theme = {t["theme"]: t for t in res["themes"]}
    assert res["commenters"]["total"] == 11
    assert by_theme["price"]["rate"] == 0.5
    assert by_theme["price"]["share_of_cancelled"] == 1.0
    assert by_theme["buffering / streaming quality"]["rate"] is None  # 2 customers


def test_risk_tiers():
    assert analysis.risk_flags(customer(status="failed")) == ("high", ["failed payment"])
    assert analysis.risk_flags(customer(status="late", tickets=4)) == (
        "high", ["late payment and 3+ tickets", "late payment", "3-5 support tickets"])
    assert analysis.risk_flags(customer(tickets=3)) == ("medium", ["3-5 support tickets"])
    assert analysis.risk_flags(customer(tickets=2)) == (None, [])


def test_at_risk_only_active_customers_sorted():
    custs = [{**customer(0, status="late"), "customer_id": 3},
             {**customer(0, status="failed"), "customer_id": 7},
             {**customer(1, status="failed", cancelled_date="2026-01-01"), "customer_id": 1},
             {**customer(None, status="failed"), "customer_id": 2},
             {**customer(0), "customer_id": 4}]
    risk = analysis.at_risk_customers(custs, [])
    assert [(r["customer_id"], r["tier"]) for r in risk] == [(7, "high"), (3, "medium")]
    assert set(risk[0]) == {"customer_id", "plan", "monthly_fee", "tier", "reasons"}


def test_risk_ignores_cancellation_outcome_fields():
    """Leakage guard: changing cancelled_date never changes a customer's tier."""
    base = customer(0, status="late", tickets=1)
    for cancelled_date in (None, "2026-01-01", "garbage"):
        assert analysis.risk_flags({**base, "cancelled_date": cancelled_date}) \
            == analysis.risk_flags(base)
        assert analysis.risk_flags({**base, "cancelled": 1, "cancelled_date": cancelled_date}) \
            == analysis.risk_flags(base)


def test_risk_backtest_tiers():
    custs = [customer(1, status="failed")] * 5 + [customer(0, status="failed")] * 5 \
        + [customer(0)] * 6
    by_tier = {s["segment"]: s for s in analysis.risk_backtest(custs)}
    assert by_tier["high"]["rate"] == 0.5 and by_tier["none"]["rate"] == 0.0
