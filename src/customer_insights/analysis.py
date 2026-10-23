"""Customer analysis. Aggregates only; see DECISIONS.md for definitions."""
import datetime
import re

MIN_GROUP = 5  # D6: published counts from 1 to 4 are suppressed


def suppress(n):
    """Return a count safe to publish: 1-4 becomes "<5"; 0 and >=5 unchanged (D6)."""
    return "<5" if 0 < n < MIN_GROUP else n


def _publishable(total, cancelled):
    """A rate may be published only if no underlying group has 1-4 customers (D6a)."""
    return all(suppress(n) != "<5" for n in (total, cancelled, total - cancelled))


def _date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _ticket_bucket(n):
    if not isinstance(n, int) or n < 0:
        return "unknown"
    return "0" if n == 0 else "1-2" if n <= 2 else "3-5" if n <= 5 else "6+"


# D4: segments compared for association with cancelling (never as causes).
FACTORS = {
    "plan": lambda r: r["plan"] or "unknown",
    "payment status": lambda r: r["last_payment_status"] or "unknown",
    "support tickets": lambda r: _ticket_bucket(r["support_tickets"]),
    "country": lambda r: r["country"] or "unknown",
}


def cancellation_rate(customers):
    """Snapshot cancellation rate over rows with a valid `cancelled` value (D1, D2).

    Returns {"total", "cancelled", "invalid", "rate"}; `total` counts valid rows only
    and `rate` is None when there are none.
    """
    total = cancelled = invalid = 0
    for row in customers:
        value = row["cancelled"]
        if value not in (0, 1):
            invalid += 1
            continue
        total += 1
        cancelled += value
    rate = cancelled / total if total else None
    return {"total": total, "cancelled": cancelled, "invalid": invalid, "rate": rate}


def segment_rates(customers, key):
    """Cancellation counts per segment (`key` maps a row to its label), sorted by label.

    `rate` is None when publishing it would expose a group of 1-4 customers.
    """
    groups = {}
    for row in customers:
        if row["cancelled"] in (0, 1):
            groups.setdefault(key(row), []).append(row)
    out = []
    for segment in sorted(groups, key=str):
        stats = cancellation_rate(groups[segment])
        total, cancelled = stats["total"], stats["cancelled"]
        out.append({"segment": segment, "customers": total, "cancelled": cancelled,
                    "rate": stats["rate"] if _publishable(total, cancelled) else None})
    return out


def cancellation_reasons(customers):
    """Return the main factors associated with cancelling (association, not cause; D4).

    One dict per (factor, segment) with `lift` = segment rate / overall rate, sorted by
    lift descending, then factor and segment; suppressed segments (rate None) come last.
    """
    overall = cancellation_rate(customers)["rate"]
    out = []
    for factor, key in FACTORS.items():
        for seg in segment_rates(customers, key):
            lift = seg["rate"] / overall if seg["rate"] is not None and overall else None
            out.append({"factor": factor, **seg, "lift": lift})
    return sorted(out, key=lambda d: (d["lift"] is None, -(d["lift"] or 0),
                                      d["factor"], str(d["segment"])))


def _period_start(day, period):
    if period == "year":
        return day.replace(month=1, day=1)
    return day.replace(month=3 * ((day.month - 1) // 3) + 1, day=1)


def _next_period(start, period):
    if period == "year":
        return start.replace(year=start.year + 1)
    month = start.month + 3
    return start.replace(year=start.year + month // 13, month=(month - 1) % 12 + 1)


def _period_label(start, period):
    return str(start.year) if period == "year" else f"{start.year}-Q{(start.month - 1) // 3 + 1}"


def cancellations_over_time(customers, key=FACTORS["plan"], period="year"):
    """Cancellation rate per period and segment (D13).

    rate = cancellations dated in the period / customers active at any point in it
    (signed up before the period ended and not cancelled before it started). Rows with
    a missing signup date or an inconsistent cancelled flag/date are excluded and counted.
    Returns {"rows": [{period, segment, customers, cancelled, rate}], "excluded": n}.
    """
    valid, excluded = [], 0
    for row in customers:
        signup, cancelled_on = _date(row["signup_date"]), _date(row["cancelled_date"])
        consistent = ((row["cancelled"] == 0 and row["cancelled_date"] is None)
                      or (row["cancelled"] == 1 and cancelled_on is not None))
        if signup is None or not consistent or (cancelled_on and cancelled_on < signup):
            excluded += 1
            continue
        valid.append((key(row), signup, cancelled_on))

    rows = []
    if valid:
        start = _period_start(min(s for _, s, _ in valid), period)
        last = max(c or s for _, s, c in valid)
        while start <= last:
            end = _next_period(start, period)
            counts = {}
            for segment, signup, cancelled_on in valid:
                if signup < end and (cancelled_on is None or cancelled_on >= start):
                    exposed, cancelled = counts.get(segment, (0, 0))
                    counts[segment] = (exposed + 1,
                                       cancelled + int(cancelled_on is not None and cancelled_on < end))
            for segment in sorted(counts, key=str):
                exposed, cancelled = counts[segment]
                rows.append({"period": _period_label(start, period), "segment": segment,
                             "customers": exposed, "cancelled": cancelled,
                             "rate": cancelled / exposed if _publishable(exposed, cancelled) else None})
            start = end
    return {"rows": rows, "excluded": excluded}


# D7a: themes found by keyword in untrusted comment text. The text is only matched,
# never returned, printed or stored.
COMMENT_THEMES = {
    "price": r"price\w*|expensive|cost\w*|cheaper|too much|afford\w*|fees?",
    "billing / payment": r"bill\w*|charged?|charges|payments?|refund\w*|invoice\w*|card",
    "buffering / streaming quality": r"buffer\w*|lag\w*|freez\w*|crash\w*|outage\w*|slow",
    "app update / subtitles": r"updat\w*|subtitle\w*|sync\w*",
    "content / programmes": r"programme\w*|programs?|content|catalog\w*|shows?|films?|movies?",
    "customer service": r"support|service|wait\w*|no answer|respon\w*|rude|agent\w*",
    "missing features": r"features?|missing|lack\w*",
    "wants to cancel": r"cancel\w*|unsubscrib\w*|close my account|leav\w*|quit\w*",
    "no complaints": r"no complaints?|works (?:fine|well|great)|happy|love",
}
_THEME_RX = {name: re.compile(rf"\b(?:{pattern})\b") for name, pattern in COMMENT_THEMES.items()}


def comment_themes(comments):
    """Map customer_id -> set of themes found in any of their comments (D7a)."""
    themes = {}
    for row in comments:
        text = (row["comment_text"] or "").lower()
        found = themes.setdefault(row["customer_id"], set())
        found.update(name for name, rx in _THEME_RX.items() if rx.search(text))
    return themes


def comment_reasons(customers, comments):
    """Cancellation rate among commenting customers whose comments mention each theme.

    Population: customers with at least one comment and a valid `cancelled` flag.
    Returns {"commenters": cancellation_rate(...), "themes": [{theme, customers,
    cancelled, rate, lift, share_of_cancelled}]} sorted like cancellation_reasons.
    """
    themes = comment_themes(comments)
    commenters = [r for r in customers
                  if r["customer_id"] in themes and r["cancelled"] in (0, 1)]
    base = cancellation_rate(commenters)
    out = []
    for name in COMMENT_THEMES:
        group = [r for r in commenters if name in themes[r["customer_id"]]]
        seg = segment_rates(group, lambda r: name)
        if not seg:
            continue
        seg = seg[0]
        published = seg["rate"] is not None and base["rate"]
        out.append({"theme": name, "customers": seg["customers"],
                    "cancelled": seg["cancelled"], "rate": seg["rate"],
                    "lift": seg["rate"] / base["rate"] if published else None,
                    "share_of_cancelled": seg["cancelled"] / base["cancelled"]
                    if published else None})
    out.sort(key=lambda d: (d["lift"] is None, -(d["lift"] or 0), d["theme"]))
    return {"commenters": base, "themes": out}


def _tickets(row):
    n = row["support_tickets"]
    return n if isinstance(n, int) else 0


# D5a: declared rules on features only. `cancelled` and `cancelled_date` are never used
# here; callers select the population (active customers).
RISK_RULES = (
    ("high", "failed payment", lambda r: r["last_payment_status"] == "failed"),
    ("high", "6+ support tickets", lambda r: _tickets(r) >= 6),
    ("high", "late payment and 3+ tickets",
     lambda r: r["last_payment_status"] == "late" and _tickets(r) >= 3),
    ("medium", "late payment", lambda r: r["last_payment_status"] == "late"),
    ("medium", "3-5 support tickets", lambda r: 3 <= _tickets(r) <= 5),
)
TIERS = ("high", "medium")


def risk_flags(row):
    """(tier, reasons) for one customer; tier is None when no rule fires."""
    reasons = [(tier, why) for tier, why, rule in RISK_RULES if rule(row)]
    if not reasons:
        return None, []
    tier = min((tier for tier, _ in reasons), key=TIERS.index)
    return tier, [why for _, why in reasons]


def at_risk_customers(customers, comments):
    """Return active customers most likely to cancel (D5a), high tier first, then by id.

    `comments` is accepted for interface compatibility but unused: comment themes did
    not separate leavers from stayers (D5a). Individual-level output: never publish it.
    Each item has customer_id, plan, monthly_fee, tier and reasons; no contact details.
    """
    out = []
    for row in customers:
        if row["cancelled"] != 0:
            continue
        tier, reasons = risk_flags(row)
        if tier:
            out.append({"customer_id": row["customer_id"], "plan": row["plan"],
                        "monthly_fee": row["monthly_fee"], "tier": tier, "reasons": reasons})
    return sorted(out, key=lambda d: (TIERS.index(d["tier"]), d["customer_id"]))


def risk_backtest(customers):
    """Historical cancellation rate per tier when the rules are applied to every customer
    (tier "none" when no rule fires); validates the rules, it does not train them."""
    return segment_rates(customers, lambda r: risk_flags(r)[0] or "none")
