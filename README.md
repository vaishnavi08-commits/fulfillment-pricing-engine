# Fulfillment Pricing Engine

A small, tested Python engine that **quotes** fulfillment orders from a rate card and **audits** a 3PL invoice line by line, flagging billing errors and the dollar impact.

## Problem

Fulfillment invoices bundle many small charges (pick, pack, storage, shipping) across thousands of orders. A wrong rate, a forgotten volume discount or a parcel billed in the wrong weight band is a few dollars per order, but it compounds across a month and erodes merchant trust. Billing logic has to be **explicit, deterministic and testable**, so finance, support and the merchant all get the same number.

## Pricing model (`data/rate_card.json`)

| Component | Rule |
|---|---|
| Pick fee | $2.50 per order + $0.50 per extra item |
| Packaging | $0.75 per order |
| Storage | $5.00 per bin per month |
| Shipping | Carrier cost by weight band (≤1, ≤5, ≤10, ≤20, ≤50 lb) **+12% cost-plus margin** |
| Volume discount | >1,000 orders/month → 10% off pick fees |

- Money is `Decimal`, rounded half-up to the cent, so quotes and audits agree to the penny.
- Weight bands are upper-bound inclusive (1.0 lb is in the ≤1 lb band).
- Pricing lives in JSON, not code: changing a rate never needs a deploy of logic.

## How it works

- `quote(order, rate_card, monthly_orders)` → breakdown: pick fee, discount, packaging, shipping (+ underlying carrier cost), total.
- `check_invoice(invoice, orders, rate_card)` → recalculates every line and flags:
  - `wrong_rate` (pick, packaging or storage)
  - `missing_discount`
  - `carrier_overcharge` / `carrier_undercharge`
  - `unbilled_order` (order shipped, never billed) and `unknown_order` (billed, never shipped)
  - plus total over-billed, under-billed and net.

## Run it

```bash
pip install -r requirements.txt
python cli.py report              # audit data/invoice.json
python cli.py quote ORD-1004      # price one order
python -m pytest -v               # 8 tests
python generate_sample_data.py    # rebuild sample orders + invoice
```

## Sample data

- 20 orders (`data/orders.json`) for a merchant shipping 1,240 orders/month (qualifies for the discount), 40 storage bins.
- `data/invoice.json` has **3 deliberate errors**:
  1. ORD-1007: extra items billed at $0.75 instead of $0.50
  2. ORD-1012: volume discount not applied
  3. ORD-1018: 4.2 lb parcel billed in the 10–20 lb carrier band

## Sample output

```
Invoice INV-2026-10-ACME | Acme Home Goods | 2026-10
Lines checked: 20 orders + storage (monthly volume 1,240)

Order      Error                Field            Billed  Expected   Impact
--------------------------------------------------------------------------
ORD-1007   Wrong rate           pick_fee           4.00      3.50    +0.50
ORD-1012   Missing discount     pick_discount      0.00      0.30    +0.30
ORD-1018   Carrier overcharge   shipping          18.93      8.74   +10.19

Billed total:   $483.88
Expected total: $472.89

3 billing errors found, $10.99 overcharged, $0.00 undercharged
```

That's 2.3% over-billing on 20 orders. If the same error rate held across all 1,240 orders, it would add up to roughly $680 a month for this one merchant.

## What I'd build next

- **Rate card versioning**: effective dates, so October invoices are audited against October rates.
- **Dimensional weight**: bill on max(actual, L×W×H / DIM factor), the most common real carrier dispute.
- **Tiered and per-merchant contracts**: multiple discount tiers, negotiated overrides, minimum monthly fees.
- **Surcharges**: fuel, residential, peak season, as configurable rules.
- **Carrier invoice reconciliation**: compare what the carrier billed us vs. what we billed the merchant, to protect margin.
- **LLM layer**: plain-English explanations of each flagged line for merchant support, and parsing PDF invoices into this JSON shape.
- **Scale**: stream large invoices, store audit results, alert finance when error rate passes a threshold.
