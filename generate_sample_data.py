"""Regenerate data/orders.json and data/invoice.json.

Builds a correct invoice from the rate card, then injects 3 deliberate errors:
  1. ORD-1007  wrong rate      - extra items billed at $0.75 instead of $0.50
  2. ORD-1012  missing discount - 10% volume discount on pick fees not applied
  3. ORD-1018  carrier overcharge - 4.2 lb parcel billed in the 10-20 lb band
"""
import json

from pricing_engine import DATA_DIR, load_rate_card, money, quote, storage_charge

# (items, weight_lb) for ORD-1001 .. ORD-1020
ORDER_SPECS = [
    (1, 0.6), (2, 1.4), (1, 0.9), (4, 6.5), (1, 2.2),
    (3, 3.1), (3, 2.8), (1, 0.4), (6, 12.0), (2, 4.9),
    (1, 1.0), (2, 1.8), (5, 9.7), (1, 0.7), (8, 22.5),
    (2, 3.6), (1, 5.0), (3, 4.2), (1, 0.8), (4, 7.3),
]
MONTHLY_ORDER_VOLUME = 1240  # merchant's total orders this month -> qualifies for discount
STORAGE_BINS = 40


def main():
    rate_card = load_rate_card()
    orders = [{"order_id": f"ORD-{1001 + i}", "items": items, "weight_lb": w}
              for i, (items, w) in enumerate(ORDER_SPECS)]

    lines = []
    for o in orders:
        q = quote(o, rate_card, MONTHLY_ORDER_VOLUME)
        lines.append({k: float(q[k]) for k in ("pick_fee", "pick_discount", "packaging_fee", "shipping")}
                     | {"order_id": o["order_id"]})

    by_id = {l["order_id"]: l for l in lines}
    by_id["ORD-1007"]["pick_fee"] = 4.00          # 2.50 + 2 x 0.75 (should be 3.50)
    by_id["ORD-1012"]["pick_discount"] = 0.00     # should be 0.30
    by_id["ORD-1018"]["shipping"] = float(money(16.90 * 1.12))  # 10-20 lb band (should be 8.74)

    storage_amount = float(storage_charge(STORAGE_BINS, rate_card))
    total = sum(l["pick_fee"] - l["pick_discount"] + l["packaging_fee"] + l["shipping"] for l in lines)
    invoice = {
        "invoice_id": "INV-2026-10-ACME",
        "merchant": "Acme Home Goods",
        "period": "2026-10",
        "monthly_order_volume": MONTHLY_ORDER_VOLUME,
        "lines": [{"order_id": l.pop("order_id"), **l} for l in lines],
        "storage": {"bins": STORAGE_BINS, "amount": storage_amount},
        "total": round(total + storage_amount, 2),
    }

    (DATA_DIR / "orders.json").write_text(json.dumps(orders, indent=2) + "\n")
    (DATA_DIR / "invoice.json").write_text(json.dumps(invoice, indent=2) + "\n")
    print("Wrote data/orders.json and data/invoice.json")


if __name__ == "__main__":
    main()
