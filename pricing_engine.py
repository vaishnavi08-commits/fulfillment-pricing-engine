"""Fulfillment Pricing Engine: quote orders and audit invoices against a rate card.

All money is handled as Decimal and rounded half-up to the cent, so a quote
and an audit of the same order always agree to the penny.
"""
from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CENT = Decimal("0.01")
CHARGE_FIELDS = ("pick_fee", "pick_discount", "packaging_fee", "shipping")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def load_json(path):
    return json.loads(Path(path).read_text())


def load_rate_card(path=DATA_DIR / "rate_card.json") -> dict:
    return load_json(path)


# ---------- pricing ----------

def carrier_base_cost(weight_lb: float, rate_card: dict) -> Decimal:
    """Carrier's cost to us, from the first weight band the parcel fits in."""
    if weight_lb <= 0:
        raise ValueError(f"weight must be positive, got {weight_lb}")
    for band in rate_card["carrier"]["weight_bands"]:
        if weight_lb <= band["max_lb"]:
            return Decimal(str(band["cost"]))
    raise ValueError(f"{weight_lb} lb exceeds the heaviest weight band")


def qualifies_for_volume_discount(monthly_orders: int, rate_card: dict) -> bool:
    return monthly_orders > rate_card["volume_discount"]["min_monthly_orders"]


def quote(order: dict, rate_card: dict, monthly_orders: int = 0) -> dict:
    """Price one order. Returns a line-by-line breakdown plus total."""
    items = order["items"]
    if items < 1:
        raise ValueError(f"{order['order_id']}: order needs at least 1 item")

    pick = rate_card["pick"]
    pick_fee = money(Decimal(str(pick["per_order"]))
                     + Decimal(str(pick["per_extra_item"])) * (items - 1))

    discount = money(0)
    if qualifies_for_volume_discount(monthly_orders, rate_card):
        pct = Decimal(str(rate_card["volume_discount"]["pick_discount_pct"]))
        discount = money(pick_fee * pct / 100)

    packaging = money(rate_card["packaging_fee_per_order"])

    carrier_cost = carrier_base_cost(order["weight_lb"], rate_card)
    margin = Decimal(str(rate_card["carrier"]["margin_pct"]))
    shipping = money(carrier_cost * (1 + margin / 100))

    return {
        "order_id": order["order_id"],
        "pick_fee": pick_fee,
        "pick_discount": discount,
        "packaging_fee": packaging,
        "shipping": shipping,
        "carrier_cost": money(carrier_cost),
        "total": pick_fee - discount + packaging + shipping,
    }


def storage_charge(bins: int, rate_card: dict) -> Decimal:
    return money(Decimal(bins) * Decimal(str(rate_card["storage_fee_per_bin_per_month"])))


# ---------- invoice audit ----------

def _classify(field: str, billed: Decimal, expected: Decimal) -> str:
    if field == "pick_discount" and billed < expected:
        return "missing_discount"
    if field == "shipping":
        return "carrier_overcharge" if billed > expected else "carrier_undercharge"
    return "wrong_rate"


def _line_total(line: dict) -> Decimal:
    return (money(line["pick_fee"]) - money(line["pick_discount"])
            + money(line["packaging_fee"]) + money(line["shipping"]))


def check_invoice(invoice: dict, orders: list[dict], rate_card: dict) -> dict:
    """Recalculate every invoice line and flag mismatches.

    impact > 0 means the merchant was overcharged; < 0 means undercharged.
    """
    orders_by_id = {o["order_id"]: o for o in orders}
    monthly = invoice["monthly_order_volume"]
    issues, billed_total, expected_total = [], Decimal(0), Decimal(0)
    billed_ids = set()

    for line in invoice["lines"]:
        oid = line["order_id"]
        billed_ids.add(oid)
        billed_total += _line_total(line)
        order = orders_by_id.get(oid)
        if order is None:
            issues.append({"order_id": oid, "field": "line", "type": "unknown_order",
                           "billed": _line_total(line), "expected": money(0),
                           "impact": _line_total(line)})
            continue

        q = quote(order, rate_card, monthly)
        expected_total += q["total"]
        for field in CHARGE_FIELDS:
            billed, expected = money(line[field]), q[field]
            if billed != expected:
                sign = -1 if field == "pick_discount" else 1  # a discount reduces the bill
                issues.append({"order_id": oid, "field": field,
                               "type": _classify(field, billed, expected),
                               "billed": billed, "expected": expected,
                               "impact": (billed - expected) * sign})

    for oid in orders_by_id.keys() - billed_ids:
        q = quote(orders_by_id[oid], rate_card, monthly)
        expected_total += q["total"]
        issues.append({"order_id": oid, "field": "line", "type": "unbilled_order",
                       "billed": money(0), "expected": q["total"], "impact": -q["total"]})

    storage = invoice["storage"]
    billed_storage = money(storage["amount"])
    expected_storage = storage_charge(storage["bins"], rate_card)
    billed_total += billed_storage
    expected_total += expected_storage
    if billed_storage != expected_storage:
        issues.append({"order_id": "STORAGE", "field": "storage", "type": "wrong_rate",
                       "billed": billed_storage, "expected": expected_storage,
                       "impact": billed_storage - expected_storage})

    over = sum((i["impact"] for i in issues if i["impact"] > 0), Decimal(0))
    under = -sum((i["impact"] for i in issues if i["impact"] < 0), Decimal(0))
    return {
        "issues": issues,
        "billed_total": billed_total,
        "expected_total": expected_total,
        "overbilled": over,
        "underbilled": under,
        "net": billed_total - expected_total,
        "stated_total_matches": money(invoice["total"]) == billed_total,
    }
