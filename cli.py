"""CLI: audit an invoice or quote a single order.

  python cli.py report                 # audit data/invoice.json
  python cli.py quote ORD-1004         # price breakdown for one order
"""
import argparse

from pricing_engine import DATA_DIR, check_invoice, load_json, load_rate_card, quote

LABELS = {
    "wrong_rate": "Wrong rate",
    "missing_discount": "Missing discount",
    "carrier_overcharge": "Carrier overcharge",
    "carrier_undercharge": "Carrier undercharge",
    "unknown_order": "Unknown order",
    "unbilled_order": "Unbilled order",
}


def report(args):
    rate_card = load_rate_card(args.rate_card)
    invoice = load_json(args.invoice)
    orders = load_json(args.orders)
    r = check_invoice(invoice, orders, rate_card)

    print(f"Invoice {invoice['invoice_id']} | {invoice['merchant']} | {invoice['period']}")
    print(f"Lines checked: {len(invoice['lines'])} orders + storage "
          f"(monthly volume {invoice['monthly_order_volume']:,})\n")
    if r["issues"]:
        print(f"{'Order':<10} {'Error':<20} {'Field':<14} {'Billed':>8} {'Expected':>9} {'Impact':>8}")
        print("-" * 74)
        for i in r["issues"]:
            print(f"{i['order_id']:<10} {LABELS[i['type']]:<20} {i['field']:<14} "
                  f"{i['billed']:>8} {i['expected']:>9} {i['impact']:>+8}")
        print()
    print(f"Billed total:   ${r['billed_total']:,.2f}")
    print(f"Expected total: ${r['expected_total']:,.2f}")
    if not r["stated_total_matches"]:
        print("WARNING: invoice's stated total doesn't match the sum of its lines")
    n = len(r["issues"])
    print(f"\n{n} billing error{'s' if n != 1 else ''} found, "
          f"${r['overbilled']:,.2f} overcharged, ${r['underbilled']:,.2f} undercharged")


def quote_cmd(args):
    rate_card = load_rate_card(args.rate_card)
    orders = {o["order_id"]: o for o in load_json(args.orders)}
    o = orders[args.order_id]
    q = quote(o, rate_card, args.monthly_orders)
    print(f"{o['order_id']}: {o['items']} item(s), {o['weight_lb']} lb, "
          f"monthly volume {args.monthly_orders:,}")
    print(f"  Pick fee        ${q['pick_fee']:>7}")
    print(f"  Volume discount -${q['pick_discount']:>6}")
    print(f"  Packaging       ${q['packaging_fee']:>7}")
    print(f"  Shipping        ${q['shipping']:>7}   (carrier cost ${q['carrier_cost']} "
          f"+ {rate_card['carrier']['margin_pct']}%)")
    print(f"  Total           ${q['total']:>7}")


def main():
    p = argparse.ArgumentParser(description="Fulfillment Pricing Engine")
    p.add_argument("--rate-card", default=DATA_DIR / "rate_card.json")
    p.add_argument("--orders", default=DATA_DIR / "orders.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="audit an invoice")
    r.add_argument("--invoice", default=DATA_DIR / "invoice.json")
    r.set_defaults(func=report)
    q = sub.add_parser("quote", help="quote one order")
    q.add_argument("order_id")
    q.add_argument("--monthly-orders", type=int, default=1240)
    q.set_defaults(func=quote_cmd)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
