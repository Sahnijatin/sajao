# Build plan: stages, affiliate setup and training data

Things with fixed waiting time, to start early: Apple and Google developer accounts, app store review, affiliate network approvals, the first brand conversations, and measuring the golden set of rooms.

## Stages to MVP

### Stage 0: foundations

- [ ] Monorepo layout, CI, lint, environments, secrets handling
- [ ] Supabase project: auth, Postgres, pgvector, storage
- [ ] Expo app shell running on one Android phone and one iPhone
- [ ] Design tokens ported from LiveMap (colour, glass, shadows, motion curves)
- [ ] Apple and Google developer accounts opened
- [ ] One-page landing site live (needed for affiliate applications)
- [ ] Apply to Cuelinks, EarnKaro, vCommission and Flipkart Affiliate
- [ ] Start the golden set: tape-measure the first 5 rooms

### Stage 1: capture and reconstruction spike (the riskiest stage)

- [ ] Golden set to 20 rooms, each filmed on 3 phone tiers including an old budget Android
- [ ] Frame selection and upload from the phone
- [ ] Reconstruction worker on serverless GPU; compare 2 or 3 candidate models; check each license
- [ ] Fit walls, floor, doors and windows into a floor plan
- [ ] Tape scaling with one and two measurements
- [ ] Benchmark script that reports wall error per room, per phone tier
- **Gate:** median wall error within target after tape check, or a written decision to launch on manual entry first

### Stage 2: room model and confirm screen

- [ ] Scene graph schema with source and confidence tags
- [ ] Quality gates (closed polygon, sanity ranges, scale agreement)
- [ ] Floor plan confirm and fix screen
- [ ] Manual entry path (room shapes, wall lengths, doors, windows)
- [ ] Existing furniture detection with keep, replace, remove
- [ ] Tape check flow with the wall highlight

### Stage 3: catalog v0

- [ ] Product schema and ingestion from 2 or 3 sources (network feed, Shopify brand feed, manual sheet)
- [ ] Dimension extraction, range validation, verified flag
- [ ] 3D pipeline: parametric templates, image-to-3D with rescale, quality check
- [ ] Embeddings per product in pgvector
- [ ] 300 living-room products loaded with sizes and 3D
- **Gate:** 3D looks right for 80% of items on a visual review

### Stage 4: solver and verifier

- [ ] Furniture program templates for the first room type
- [ ] Hard constraints and soft scores
- [ ] Layout solver, three archetypes for three variations
- [ ] Independent verifier and a unit test suite of tricky rooms
- [ ] Rearrange-only mode
- **Gate:** a designer rates 7 of 10 layouts acceptable

### Stage 5: brief to three designs, end to end

- [ ] Brief screens: checklist, budget, style swipes, reference upload, household, pincode
- [ ] Brief parser (small LLM, JSON schema, fallback)
- [ ] Retrieval with hard filters
- [ ] Design API: room plus brief in, three verified designs out
- [ ] "Why this works" templates

### Stage 6: 3D editor

- [ ] Room shell rendering in three.js, dollhouse and walk-through cameras
- [ ] Drag, rotate, snap, collision glow, live distances
- [ ] Swap carousel, lock and regenerate, live budget
- [ ] Viewer tiers: full 3D, lite 3D, 2D plan
- [ ] Editor embedded in the app and opening from a web link

### Stage 7: capture coach and first wow moments

- [ ] Coach intro animations and the live camera overlay (level, speed, coverage ring, corner ticks, warnings)
- [ ] Photo mode for weak phones
- [ ] Post-capture quality score with specific retake prompts
- [ ] Plan draws itself, tape lock, room rises, design reveal, before and after slider
- [ ] Haptics and reduced-motion handling; low-tier fallbacks

### Stage 8: commerce, events and privacy

- [ ] Redirect service with click logging and sub-IDs
- [ ] Deep links per network; whole-room list grouped by retailer
- [ ] Daily reconciliation of network reports
- [ ] Event log for every action (the future training data)
- [ ] Consent, deletion, raw video removal after reconstruction
- [ ] Catalog to 2,000 products; daily price and stock sync
- [ ] Apply to Amazon Associates close to launch, so its 180-day clock starts late

### Stage 9: hardening and beta

- [ ] Test matrix on real low-end Android phones and older iPhones
- [ ] Performance budget, crash reporting, cost-per-design dashboard
- [ ] Closed beta with real users; fix the top issues (Google Play requires a 12-tester, 14-day closed test for new personal accounts before production)
- [ ] Store listings, screenshots, submission
- **Gate:** 30 users finish a design; cost per design measured; first tracked purchase

## After MVP

- **Chat:** intent router for the 20 common requests; tool-calling LLM for the rest, behind the gateway, with caps
- **AR:** ARCore and ARKit boosters in capture; RoomPlan path on LiDAR devices; AR view of the design at true scale
- **Growth and revenue:** share links, family vote, share reel, price-drop and restock alerts, paint flood, day to night, paid photoreal render
- **v2 learning loop:** product ranker trained from the event log, golden set and replay evaluation, shadow and canary rollout, solver weight tuning from user edits

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
| [Cuelinks](https://www.cuelinks.com/campaigns/urban-ladder-affiliate-program) | One account for many Indian merchants, including Amazon India and furniture brands such as Urban Ladder (up to 5.76% per sale) | Campaigns can be paused by the advertiser; Urban Ladder was shown as paused when checked. Each campaign has its own allowed-media rules. | Stage 0 |
| [EarnKaro](https://earnkaro.com/blog/ikea-affiliate-program) | IKEA India at up to 5%, 30-day tracking window | Confirmed after 60 days. Tracking is stated to work on web and mobile web but not inside the retailer app. Shown with a paused link, so confirm it is active. | Stage 0 |
| [vCommission](https://www.vcommission.com/blog/publishers/top-indian-e-commerce-affiliate-programs-with-high-payouts-in-2026/) | Home and decor brands with an account manager | Good route to negotiate custom terms | Stage 0 |
| Flipkart Affiliate (direct) | 5 to 8% quoted on home furnishings, 7-day window | Per-order caps apply ([rates guide](https://fluxnote.io/guides/flipkart-affiliate-commission-rates-2026)) | Stage 0 |
| [Amazon Associates India](https://fluxnote.io/guides/amazon-associates-india-how-to-join-2026) (direct) | Largest catalog, 24-hour window | Needs a public site, app or channel. Requires 3 qualifying sales within 180 days or the account is closed. PAN needed. Minimum bank payout 2,500 rupees. | Stage 8 |
| Direct deals with D2C brands | Best rates, longer attribution, clean product data and 3D assets | Tracked by coupon code or server postback. Start with brands on Shopify. | From stage 3 |

What this means for the build:

- Open retailer links in the mobile browser where a program does not track in-app purchases.
- Never depend on one network. Campaigns pause without notice, so each product should carry more than one possible link.
- Read each campaign's allowed-media rules before launch and confirm that a mobile app is an accepted traffic source.
- Have a PAN and a bank account ready. Take advice from a chartered accountant on GST and on whether to register a company before signing brand contracts.

## Training: what is trained and where the data comes from

Nothing needs to be trained to ship v1. Every model at launch is pretrained or rule-based. Automated retraining is a v2 feature, built once real users exist.

| Component | At launch | Trained in v2? | Data source |
| --- | --- | --- | --- |
| Room reconstruction | Pretrained open model | Fine-tune once enough rooms exist | Our golden set (tape-measured rooms), user-confirmed measurements, LiDAR scans paired with camera-only captures |
| Furniture detection | Pretrained open-vocabulary detector | Fine-tune if errors are common | Label fixes users make on the confirm screen |
| Style matching | Pretrained image and text embedding model | No | None needed |
| Dimension extraction | Small LLM plus range rules | No | Catalog feeds |
| Layout scoring | Hand-set weights from an interior designer | Yes | Designer ratings first, then the gap between our layout and the user's final layout |
| Product ranker | Rules: style match, price fit, availability | Yes | Our event log: swaps, saves, clicks, purchases, which variation won |
| Brief parser | Small hosted LLM | Optional LoRA fine-tune at scale | Logged brief-to-spec pairs |

Notes on data:

- **Our own data is the asset.** The event log, the golden set and user-confirmed measurements are what make v2 improve. Logging ships in v1.
- **Public datasets are for evaluation and experiments first.** Indoor datasets such as ScanNet, ARKitScenes, Structured3D and 3D-FRONT are useful, but several carry research-only terms. Check each license before any commercial training.
- **Volume needed.** The ranker will not beat rules until there are a few thousand completed designs. Until then, rules plus designer-curated reference looks carry quality.
- **Privacy.** Train only on data users consented to, strip raw video after reconstruction, and keep faces and personal photos out of training sets.
