# Roadmap, risks and decisions

## Phases and gates

Sprint dates live in Notion. Each phase ends at a gate with numbers; the next phase does not start until the gate passes or a decision log entry explains why not.

| Phase | Contents | Gate |
| --- | --- | --- |
| Setup | Charter, Notion, repo guardrails, CI, accounts, affiliate sign-ups | Charter approved; CI green |
| Foundations and spikes | Design system and component gallery, app shell, schemas, API skeleton with auth and uploads, render bake-off, geometry spike, Flipkart feed ingestion | Bake-off winner and fallback chosen; geometry error bands measured on tape-measured rooms; cost per room measured |
| Room and taste | Capture with guides, room understanding pipeline, Room Profile card, adaptive swipes, curation tool, first approved products | Room Profile within targets on the golden set; enough approved products per style |
| Design engine and commerce | Spec, retrieval, designer, solver, verifier, relaxation, three intents, shopping list, redirect service, 2D plan | Zero verifier failures shown; totals match retailer prices |
| Render, plan, Vastu | Render pipeline with checks and fallbacks, reveal, plan editing, swap, Vastu tab | Render gates in [assumptions and accuracy](02-assumptions-and-accuracy.md) |
| Polish and test build | Share reel, save and history, motion and haptics pass, budget Android pass, consent and privacy | Stable build in the Play closed test and TestFlight |
| Test fixes and release candidate | Closed-test fixes, quality gates on the golden set, 3D view on capable phones, store listings | All quality gates pass; store submission |
| After launch | Subscription switched on by the founder, Next tier features, all room types if accuracy holds | Per decision |

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Renders drift from real products or change the room | Breaks visual quality and trust | Multi-reference guided edit, per-item checks, retry, 3D fallback, bake-off first |
| Photo-only dimensions too loose for small rooms | Breaks spatial credibility | Anchor cross-checks, error band as solver margin, one targeted tape request in tight spots |
| Catalog thin for some styles or budgets | Designs look generic | Flipkart feed plus networks plus D2C; weekly coverage report |
| Amazon Creators API needs qualifying sales first | Fewer Amazon items early | Manual Amazon links until eligible; Flipkart and networks carry the launch |
| Affiliate attribution leaks in retailer apps | Lower revenue | Deeplinks that track in apps, coupon codes, controlled browser tab |
| Cost spike after marketing | Budget overrun | Gateway caps, cheaper preview tier, per-user soft limits, funding |
| Play closed test needs 12 testers for 14 days | Android production access waits | Closed test starts as soon as a stable build exists; testers recruited early |
| Scope creep | Misses the store date | Notion change protocol; Must tier first, deep before wide |
| Vastu direction errors | Wrong advice | Averaged compass plus confirmation, approximate flag, consultant-reviewed rules |
| Model licenses | Legal risk | Recorded and reviewed before use |
| Privacy of home photos | Trust and legal risk | Consent, blurring, raw video deleted after processing |

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
| Launch | Public on both stores, free, no invites, then marketing | Founder decision: maximum reach from day one; testing groups run separately through store tools |
| Fallbacks | Gateway chain down to degraded mode | The app must never stop suddenly |
| Cloud budget | 5,000 to 20,000 rupees a month, funding added if needed | Founder decision |


### Charter v2 decisions

These supersede earlier rows where they conflict; earlier rows are kept as history.

| Decision | Choice | Reason |
| --- | --- | --- |
| Strategy | Transformation-first: understand room, understand taste, show possibilities, help execute | Users want their room transformed, not a design tool to operate |
| Capture | Photos or a short video; tape values optional and upgrade a room to Verified | Removes the biggest drop-off point; tape still available for exact fits |
| Dimensions | Estimated by geometry models with scale anchors and a shown error band; never set by a generative model | Honest numbers on any phone; the solver uses the band as margin |
| Non-negotiables | Visual quality, spatial credibility, commercial utility, enforced on one Design object | Render, plan and cart cannot disagree when all come from one object |
| Taste | Learned taste profile (age band as weak prior, adaptive swipes, references, behaviour) mapped onto style profiles | Fewer taps, better signal, coherent designs |
| Catalog | AI-curated from Flipkart feeds, Amazon, networks, D2C and rental, human gate on hero items | Coverage across styles and budgets with quality control |
| Render | Guided multi-reference edit of your photo, chosen by blind bake-off, checked, 3D fallback | Exciting images that keep the room and the real products |
| Revenue | Affiliate on every buy and rent route plus subscription; entitlements built, off at launch | Founder decision; revenue from day one without a paywall |
| Cost per room | Best quality at about Rs 30 to 40 | Founder decision |
| Login | Truecaller, Google, Apple, WhatsApp OTP fallback; guest first, sign-in before generation | Lowest friction in India; protects cost per room |
| Room types | Living room and bedroom first; all room types before launch only if testing shows accuracy, via a scope change | Founder decision |
| Vastu | Own tab: room-level now; floor plans, expert call and home visit later | Founder decision |
| Infrastructure | Supabase Postgres, R2, Cloud Run, Modal, one model gateway, durable jobs | Scales from 10 to 1 lakh users without a rebuild |
| Tracking | Notion is the single tracker; scope changes need founder approval | Prevents drift |
| Skills in repo | Licensed third-party skills copied into `.claude/skills/` instead of declared as plugins | Cloud sessions do not reliably install plugins; copies are versioned with the code |

Open: final product name after domain, store and trademark checks.
