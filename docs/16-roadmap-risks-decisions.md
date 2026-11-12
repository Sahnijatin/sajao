# Roadmap, risks and decisions

## Phases and gates

Each gate has a number. The next phase does not start until the gate passes or a decision log entry explains why not.

### Phase 0: proof spikes

| Spike | Gate |
| --- | --- |
| Golden set | At least 20 rooms measured to truth, scanned on every device matrix phone |
| Tape-entry room model | Median dimension error 1% or less, 90th percentile 2% or less |
| Door and window positions from scan | Median error 10 cm or less after confirm |
| Reconstruction-only dimensions (experiment) | Reported per phone tier; tape becomes optional on a tier only at median 1% or less and 90th percentile 2% or less |
| Catalog v0 | 100 curated items with 3D; 80% or more pass visual review; every item has a permitted affiliate route |
| Design engine | On 50 golden rooms, at least 90% produce a verified design without relaxation step 5; every room produces an honest result |
| Taste | Our designs preferred over references in at least 50% of at least 200 blind votes |
| Photo render | At least 95% of items pass the outline check (85% overlap) |
| Cost and latency | Cost per room and stage latencies measured on the default path |

### Phase 1: v1 launch (the Must tier)

Gate: 30 or more beta users complete a design, including on the budget Android; crash-free sessions 99% or more; cost per room within the default-path estimate; first tracked purchases.

### Phase 2: after launch

Next-tier features; paywall switched on only when revenue per room is at least 3 times cost per room over 30 days, or by an explicit decision log entry.

### Phase 3: v2 learning

Gate: a new model must beat the current one on every evaluation slice with confidence intervals not overlapping a regression.

## Risks

| Risk | Mitigation |
| --- | --- |
| Reconstruction weak on white walls and glossy tile | Tape sets dimensions; scan only proposes; walking loop for parallax |
| Small rooms cannot fit the brief | Relaxation order and honest result |
| Renders drift from products | 3D-first composite, low-strength harmonization, outline and likeness checks, 3D fallback, illustrative label |
| Attribution leaks to retailer apps and later purchases | Coupon codes first, controlled browser tab, re-engagement links |
| Catalog is the bottleneck | Started as its own workstream now; few hundred items for v1 |
| Permissions for brand images and creator content | Logged before use; brands via programs or deals that cover image use |
| Cost spike at launch | Invites, caps, fallback chain, funding |
| Cold starts | Staged reveal, warm peak hours, memory snapshots |
| Vastu direction errors | Three-source direction, approximate flag, expert-reviewed rules |
| Model licenses | Recorded and reviewed before use |
| Privacy | Consent, raw video deleted after processing, blurring |

## Decision log

| Decision | Choice | Reason |
| --- | --- | --- |
| Market and devices | India, any phone | Most target users are on Android, many on older phones |
| Room types | Living room and bedroom | Highest spend and strongest Vastu demand; chosen by the founder |
| Dimensions | Tape entry on a scan-drafted plan | Camera reconstruction cannot back fit claims on typical Indian surfaces; tape is about 1 cm accurate on every phone |
| Role of the scan | Shape proposal, openings, items, masks, camera positions | Keeps the visual magic without trusting it for numbers |
| Design approach | AI designer, archetypes, solver, verifier, relaxation order | Research shows models need grounded checks; archetypes cover repeated Indian layouts |
| Infeasible rooms | Honest result instead of a forced design | A design that fails the verifier is never shown |
| Result presentation | 3D first, illustrative photo render after | Exactness lives in 3D; renders are for desire |
| Catalog | Curated brands with permitted, app-safe routes | Taste is the product; permissions are required for images |
| Attribution | Coupon codes first, tracked links second | Codes survive app switching and delayed purchases |
| Vastu | Room-level in v1, whole-home next | Room-level needs only the scanned room; whole-home needs plan reading |
| Own trained models | Next tier | Need vote and curation data that does not exist yet |
| Design system | LiveMap tokens, motion and haptics | Proven premium look; consistent across products |
| 3D renderer | react-native-filament | Native performance on budget phones |
| Launch | Free, invite-based, no paywall in the app | Control load and cost, build anticipation |
| Fallbacks | Gateway chain down to degraded mode | The app must never stop suddenly |
| Cloud budget | 5,000 to 20,000 rupees a month, funding added if needed | Founder decision |

Open: final product name after domain, store and trademark checks.
