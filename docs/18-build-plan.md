# Build plan: timeline, sprints, affiliate setup and training data

A solo build working daily with an AI coding assistant reaches a store-ready MVP in about 120 working days (10 two-week sprints) and the full version 1 in about 170 working days (14 sprints). Both figures are estimates.

## Timeline assumptions

- One person, 6 days a week, about 5 to 6 focused hours a day. Sprints are 2 weeks, so 12 working days each.
- Writing code is not the bottleneck. The slow parts are tuning reconstruction on real rooms, catalog data, testing on real budget phones, and waiting on approvals.
- Full-time days (8 to 10 hours) shorten this by roughly a quarter, not by half, because the waits do not compress.
- Realistic range for the MVP: 100 to 140 working days. The main swing factor is sprint 1. If camera-only reconstruction misses the accuracy target, add 2 to 4 weeks or lean harder on manual entry for launch.

Things with fixed waiting time, to start early: Apple and Google developer accounts, app store review, affiliate network approvals, the first brand conversations, and measuring the golden set of rooms.

## Sprints to MVP

### Sprint 0 (1 week): foundations

- [ ] Monorepo layout, CI, lint, environments, secrets handling
- [ ] Supabase project: auth, Postgres, pgvector, storage
- [ ] Expo app shell running on one Android phone and one iPhone
- [ ] Design tokens ported from LiveMap (colour, glass, shadows, motion curves)
- [ ] Apple and Google developer accounts opened
- [ ] One-page landing site live (needed for affiliate applications)
- [ ] Apply to Cuelinks, EarnKaro, vCommission and Flipkart Affiliate
- [ ] Start the golden set: tape-measure the first 5 rooms

### Sprint 1: capture and reconstruction spike (the riskiest sprint)

- [ ] Golden set to 20 rooms, each filmed on 3 phone tiers including an old budget Android
- [ ] Frame selection and upload from the phone
- [ ] Reconstruction worker on serverless GPU; compare 2 or 3 candidate models; check each license
- [ ] Fit walls, floor, doors and windows into a floor plan
- [ ] Tape scaling with one and two measurements
- [ ] Benchmark script that reports wall error per room, per phone tier
- **Gate:** median wall error within target after tape check, or a written decision to launch on manual entry first

### Sprint 2: room model and confirm screen

- [ ] Scene graph schema with source and confidence tags
- [ ] Quality gates (closed polygon, sanity ranges, scale agreement)
- [ ] Floor plan confirm and fix screen
- [ ] Manual entry path (room shapes, wall lengths, doors, windows)
- [ ] Existing furniture detection with keep, replace, remove
- [ ] Tape check flow with the wall highlight

### Sprint 3: catalog v0

- [ ] Product schema and ingestion from 2 or 3 sources (network feed, Shopify brand feed, manual sheet)
- [ ] Dimension extraction, range validation, verified flag
- [ ] 3D pipeline: parametric templates, image-to-3D with rescale, quality check
- [ ] Embeddings per product in pgvector
- [ ] 300 living-room products loaded with sizes and 3D
- **Gate:** 3D looks right for 80% of items on a visual review

### Sprint 4: solver and verifier

- [ ] Furniture program templates for the first room type
- [ ] Hard constraints and soft scores
- [ ] Layout solver, three archetypes for three variations
- [ ] Independent verifier and a unit test suite of tricky rooms
- [ ] Rearrange-only mode
- **Gate:** a designer rates 7 of 10 layouts acceptable

### Sprint 5: brief to three designs, end to end

- [ ] Brief screens: checklist, budget, style swipes, reference upload, household, pincode
- [ ] Brief parser (small LLM, JSON schema, fallback)
- [ ] Retrieval with hard filters
- [ ] Design API: room plus brief in, three verified designs out
- [ ] "Why this works" templates

### Sprint 6: 3D editor

- [ ] Room shell rendering in three.js, dollhouse and walk-through cameras
- [ ] Drag, rotate, snap, collision glow, live distances
- [ ] Swap carousel, lock and regenerate, live budget
- [ ] Viewer tiers: full 3D, lite 3D, 2D plan
- [ ] Editor embedded in the app and opening from a web link

### Sprint 7: capture coach and first wow moments

- [ ] Coach intro animations and the live camera overlay (level, speed, coverage ring, corner ticks, warnings)
- [ ] Photo mode for weak phones
- [ ] Post-capture quality score with specific retake prompts
- [ ] Plan draws itself, tape lock, room rises, design reveal, before and after slider
- [ ] Haptics and reduced-motion handling; low-tier fallbacks

### Sprint 8: commerce, events and privacy

- [ ] Redirect service with click logging and sub-IDs
- [ ] Deep links per network; whole-room list grouped by retailer
- [ ] Daily reconciliation of network reports
- [ ] Event log for every action (the future training data)
- [ ] Consent, deletion, raw video removal after reconstruction
- [ ] Catalog to 2,000 products; daily price and stock sync
- [ ] Apply to Amazon Associates now, so its 180-day clock starts close to launch

### Sprint 9: hardening and beta

- [ ] Test matrix on real low-end Android phones and older iPhones
- [ ] Performance budget, crash reporting, cost-per-design dashboard
- [ ] Closed beta with 30 real users; fix the top issues
- [ ] Store listings, screenshots, submission
- **Gate:** 30 users finish a design; cost per design measured; first tracked purchase

## Sprints after MVP

### Sprint 10: chat

- [ ] Intent router for the 20 common requests
- [ ] Tool-calling LLM for the rest, behind the gateway, with caps

### Sprint 11: AR

- [ ] ARCore and ARKit boosters in capture; RoomPlan path on LiDAR devices
- [ ] AR view of the design at true scale

### Sprint 12: learning loop

- [ ] Training job for the product ranker from the event log
- [ ] Golden set and replay evaluation, worst-slice rule
- [ ] Shadow, 5% canary, auto promote and rollback
- [ ] Solver soft-weight tuning from user edits

### Sprint 13: growth and revenue features

- [ ] Share links, family vote, share reel
- [ ] Price-drop and restock alerts
- [ ] Paint flood, day to night, remaining wow moments
- [ ] Paid photoreal render

## Affiliate: how it works

1. She taps an item. The app calls our redirect service, which logs the click with a unique ID.
2. The redirect forwards to the retailer through a tracking link that carries that ID.
3. She buys on the retailer's site or app. The retailer reports the order to the network.
4. The order shows as pending within a day or two, and is confirmed only after the return window, often 30 to 60 days.
5. The network pays out after confirmation. Cash from a sale typically arrives 2 to 3 months later.
6. A daily job matches network reports to our click IDs to give revenue per design.

## Affiliate: where to enroll

| Where | What it gives | Notes | When |
| --- | --- | --- | --- |
| [Cuelinks](https://www.cuelinks.com/campaigns/urban-ladder-affiliate-program) | One account for many Indian merchants, including Amazon India and furniture brands such as Urban Ladder (up to 5.76% per sale) | Campaigns can be paused by the advertiser; Urban Ladder was shown as paused when checked. Each campaign has its own allowed-media rules. | Sprint 0 |
| [EarnKaro](https://earnkaro.com/blog/ikea-affiliate-program) | IKEA India at up to 5%, 30-day tracking window | Confirmed after 60 days. Tracking is stated to work on web and mobile web but not inside the retailer app. Shown with a paused link, so confirm it is active. | Sprint 0 |
| [vCommission](https://www.vcommission.com/blog/publishers/top-indian-e-commerce-affiliate-programs-with-high-payouts-in-2026/) | Home and decor brands with an account manager | Good route to negotiate custom terms | Sprint 0 |
| Flipkart Affiliate (direct) | 5 to 8% quoted on home furnishings, 7-day window | Per-order caps apply ([rates guide](https://fluxnote.io/guides/flipkart-affiliate-commission-rates-2026)) | Sprint 0 |
| [Amazon Associates India](https://fluxnote.io/guides/amazon-associates-india-how-to-join-2026) (direct) | Largest catalog, 24-hour window | Needs a public site, app or channel. Requires 3 qualifying sales within 180 days or the account is closed. PAN needed. Minimum bank payout 2,500 rupees. | Sprint 8 |
| Direct deals with D2C brands | Best rates, longer attribution, clean product data and 3D assets | Tracked by coupon code or server postback. Start with brands on Shopify. | From sprint 3 |

What this means for the build:

- Open retailer links in the mobile browser where a program does not track in-app purchases.
- Never depend on one network. Campaigns pause without notice, so each product should carry more than one possible link.
- Read each campaign's allowed-media rules before launch and confirm that a mobile app is an accepted traffic source.
- Have a PAN and a bank account ready. Take advice from a chartered accountant on GST and on whether to register a company before signing brand contracts.

## Training: what is trained and where the data comes from

Nothing needs to be trained to ship the MVP. Every model at launch is pretrained or rule-based. The first real training is the product ranker in sprint 12, on our own usage data.

| Component | At launch | Trained later? | Data source |
| --- | --- | --- | --- |
| Room reconstruction | Pretrained open model | Fine-tune once enough rooms exist | Our golden set (tape-measured rooms), user-confirmed measurements, LiDAR scans paired with camera-only captures |
| Furniture detection | Pretrained open-vocabulary detector | Fine-tune if errors are common | Label fixes users make on the confirm screen |
| Style matching | Pretrained image and text embedding model | No | None needed |
| Dimension extraction | Small LLM plus range rules | No | Catalog feeds |
| Layout scoring | Hand-set weights from an interior designer | Yes, weekly | Designer ratings of about 200 generated layouts first, then the gap between our layout and the user's final layout |
| Product ranker | Rules: style match, price fit, availability | Yes, nightly | Our event log: swaps, saves, clicks, purchases, which variation won |
| Brief parser | Small hosted LLM | Optional LoRA fine-tune at scale | Logged brief-to-spec pairs |

Notes on data:

- **Our own data is the asset.** The event log, the golden set and user-confirmed measurements are what make the system improve. Logging starts in sprint 8, before launch.
- **Public datasets are for evaluation and experiments first.** Indoor datasets such as ScanNet, ARKitScenes, Structured3D and 3D-FRONT are useful, but several carry research-only terms. Check each license before any commercial training.
- **Volume needed.** The ranker will not beat rules until there are a few thousand completed designs. Until then, rules plus about 200 designer-curated reference looks carry quality.
- **Privacy.** Train only on data users consented to, strip raw video after reconstruction, and keep faces and personal photos out of training sets.
