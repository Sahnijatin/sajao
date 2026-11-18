# Commerce and monetization

Revenue comes from affiliate commissions on every buy and rent route we can use, plus a subscription that is built from day one and switched on by the founder after launch.

## On the reveal

Total cost; a breakdown by category (furniture, lighting, decor, paint litres from wall area, flooring); a cheaper alternative per item; buy or rent per item; the whole list grouped by retailer. Budget and stock are re-checked at reveal time.

## Attribution

Furniture is often bought days later, frequently inside the retailer's own app. The design reduces the leak:

1. **Deeplinks that track in apps** where the program supports it (Flipkart does).
2. **Brand coupon codes** for direct D2C deals. A code works on any device, in any app, days later.
3. **Redirect service.** Every buy or rent tap gets a click ID (user, design, product, position) and opens in a browser tab we control. The API (`POST /v1/clicks`) takes the link from the product as the user's design showed it, refuses a product out of stock, logs the tap once per click ID, and puts the click ID in the network's sub-id parameter where the retailer has one (Flipkart `affExtParam1`, Amazon `ascsubtag`).
4. **Re-engagement.** Saved designs, price-drop and restock alerts bring you back through a fresh tracked link.
5. **Daily reconciliation** of network and brand reports against click IDs and code redemptions gives revenue per design.

Rules: more than one route per product where available; app traffic must be allowed by each campaign; no single retailer above 40% of revenue; affiliate links disclosed in the app.

## Sources

Flipkart, Amazon India, affiliate networks (Cuelinks, EarnKaro, vCommission, INRDeals), D2C brands and rental platforms. Details in [catalog](07-catalog-and-3d-assets.md). Terms are confirmed on official rate cards and recorded in Notion "Catalog sources".

## Subscription

| Plan | Draft terms |
| --- | --- |
| Room Pass | About 199 rupees one-time per room |
| Pro | About 199 rupees a month or 999 rupees a year |

Built with RevenueCat entitlements and store billing from day one, and **switched off at launch**. Until the founder switches entitlements on, no paywall, lock, upgrade prompt or paid badge appears anywhere in the app.

## Later revenue

Paid Vastu expert calls and home visits; service leads (painters, carpenters, interior firms); labelled sponsored placement that never breaks fit, budget or style filters.

## Cost protection

Per-user and per-device limits, app attestation and gateway spend caps protect the cost per room. When a cap is hit, the room waits in a queue with an honest message instead of failing.
