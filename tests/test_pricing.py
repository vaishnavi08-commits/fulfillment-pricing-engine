import copy
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pricing_engine import (DATA_DIR, check_invoice, load_json, load_rate_card,  # noqa: E402
                            quote)

D = Decimal
RATE_CARD = load_rate_card()
ORDERS = load_json(DATA_DIR / "orders.json")
INVOICE = load_json(DATA_DIR / "invoice.json")


def order(items=1, weight=0.5):
    return {"order_id": "T-1", "items": items, "weight_lb": weight}


def test_single_item_quote_breakdown():
    q = quote(order(1, 0.5), RATE_CARD, monthly_orders=0)
    assert q["pick_fee"] == D("2.50")
    assert q["packaging_fee"] == D("0.75")
    assert q["shipping"] == D("5.04")          # 4.50 + 12%
    assert q["total"] == D("8.29")
    assert quote(order(4), RATE_CARD)["pick_fee"] == D("4.00")  # 2.50 + 3 extra x 0.50


def test_weight_band_boundary_is_inclusive():
    assert quote(order(weight=1.0), RATE_CARD)["carrier_cost"] == D("4.50")
    assert quote(order(weight=1.01), RATE_CARD)["carrier_cost"] == D("7.80")


def test_overweight_or_invalid_order_rejected():
    with pytest.raises(ValueError):
        quote(order(weight=51), RATE_CARD)
    with pytest.raises(ValueError):
        quote(order(items=0), RATE_CARD)


def test_volume_discount_only_above_threshold():
    assert quote(order(2), RATE_CARD, monthly_orders=1000)["pick_discount"] == D("0.00")
    assert quote(order(2), RATE_CARD, monthly_orders=1001)["pick_discount"] == D("0.30")


def test_clean_invoice_has_no_errors():
    clean = copy.deepcopy(INVOICE)
    for line in clean["lines"]:
        o = next(x for x in ORDERS if x["order_id"] == line["order_id"])
        q = quote(o, RATE_CARD, clean["monthly_order_volume"])
        for f in ("pick_fee", "pick_discount", "packaging_fee", "shipping"):
            line[f] = float(q[f])
    r = check_invoice(clean, ORDERS, RATE_CARD)
    assert r["issues"] == []
    assert r["net"] == 0


def test_sample_invoice_flags_the_three_planted_errors():
    r = check_invoice(INVOICE, ORDERS, RATE_CARD)
    found = {(i["order_id"], i["type"]) for i in r["issues"]}
    assert found == {
        ("ORD-1007", "wrong_rate"),
        ("ORD-1012", "missing_discount"),
        ("ORD-1018", "carrier_overcharge"),
    }


def test_overbilled_total_is_exact():
    r = check_invoice(INVOICE, ORDERS, RATE_CARD)
    assert r["overbilled"] == D("10.99")       # 0.50 + 0.30 + 10.19
    assert r["underbilled"] == D("0")
    assert r["net"] == r["billed_total"] - r["expected_total"] == D("10.99")
    assert r["stated_total_matches"]


def test_missing_and_unknown_orders_are_flagged():
    inv = copy.deepcopy(INVOICE)
    dropped = inv["lines"].pop(0)                       # ORD-1001 never billed
    inv["lines"].append({**dropped, "order_id": "ORD-9999"})  # phantom order
    types = {i["type"] for i in check_invoice(inv, ORDERS, RATE_CARD)["issues"]}
    assert {"unbilled_order", "unknown_order"} <= types
