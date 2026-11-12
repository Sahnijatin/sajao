# Roadmap, risks and decisions

## Phases

Each phase has a gate. The next does not start until it passes.

| Phase | Build | Gate |
| --- | --- | --- |
| 0. Proof spikes | Golden set of measured rooms scanned on every phone tier; reconstruction benchmark of the candidate models; catalog v0 with curated products, 3D and links; design engine on real rooms | Wall error within target after the tape check. 3D looks right for 80% of items. Designs preferred to references in blind votes at an agreed rate. |
| 1. v1 launch | Everything in [principles and scope](01-bottom-line.md): capture with guides, both room types, curated catalog, design engine, reveal, editor, Vastu, buy list, share reel, event logging, entitlements switched off | Real users finish designs on budget phones. Cost per room measured. First tracked purchases. |
| 2. After launch | Enable Room Pass and Pro; live Vastu expert; AR view; service leads; more style profiles; flat-type library | Revenue per room exceeds cost per room by a clear multiple |
| 3. v2 learning | Gated retraining of the taste ranker and soft scores from usage; capture tuning from LiDAR pairs; photoreal walk-throughs on high-end phones | New models beat current ones on every evaluation slice |

## Risks

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Camera-only accuracy on budget Androids | Most of India | Tape check on every scan, two candidate models, ARCore poses when present, manual fallback |
| Renders drift from real products | Breaks trust | Geometry-conditioned renders, per-item fidelity check, 3D fallback |
| Affiliate tracking lost in retailer apps | Zero commission | Forced browser tab, app traffic rules checked, multiple routes |
| Curated brands lack affiliate programs | Thin catalog | Brand-run programs, direct deals, coupon tracking |
| Catalog data quality | Wrong sizes break the promise | Verified flag, range checks, human approval, audits |
| 3D asset quality | Ugly models kill desire | Fidelity gate, human check on hero items, cutouts for small decor |
| Vastu direction errors | Wrong advice | Three-source direction, approximate flag, expert-reviewed rules |
| GPU and model cost during free launch | Budget overrun | Render on open only, self-hosting, per-user caps, spend alerts |
| Model licenses | Some weights forbid commercial use | License review before any model enters the pipeline |
| Privacy | Videos of homes are sensitive | Consent, delete raw video after reconstruction, blur faces and personal photos, India data protection law |

## Decision log

| Decision | Choice |
| --- | --- |
| Market and devices | India, any phone, no dependence on hardware |
| Room types at launch | Living room and bedroom |
| Capture | One sweep plus a doorway sweep, one tape measurement, server reconstruction |
| Geometry authority | Measured geometry and code; never a model |
| Design approach | AI designer plus archetypes plus solver plus verifier plus critique loop |
| Result presentation | Her photo, redesigned, with fidelity checks; 3D for editing |
| Catalog | Curated brands with app-safe affiliate routes; marketplaces fill gaps |
| Vastu | Room-level and whole-home; three-source direction; expert-reviewed rules |
| Training in v1 | Small taste, compatibility and catalog models only; retraining from usage in v2 |
| Design system | LiveMap tokens, motion and haptics on both platforms |
| 3D renderer | react-native-filament |
| Launch pricing | Free; no paywall shown; entitlements off and remotely switchable |
| Later pricing | Room Pass plus Pro subscription |
| Cloud budget | 5,000 to 20,000 rupees a month with caps |

Open: final product name after domain, store and trademark checks.
