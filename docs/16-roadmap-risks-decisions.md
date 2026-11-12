# Roadmap, risks and decisions needed

Prove the three risky parts in a short spike before building the app: scan accuracy, catalog quality and the solver. Each phase has a gate; do not start the next until it passes.

| Phase | Build | Gate to pass |
| --- | --- | --- |
| 0. Proof spikes | Tape-measure 20 rooms and scan each on 3 phone tiers, including a 4-year-old budget Android. Load 300 products with sizes and 3D. Run the solver on 10 rooms. | Median wall error within target. 3D models look right for 80% of items. A designer rates 7 of 10 layouts acceptable. |
| 1. MVP | One room type, universal camera capture with capture coach and tape check, manual entry, the LiveMap-based design system, 2,000 products, 3 designs, editor, affiliate links, event logging | 30 real users finish a design. Cost per design is measured. First tracked purchases. |
| 2. Reach | AR boosters and AR mode on supported phones, full set of wow moments, chat, share links, alerts | Budget-phone accuracy within target on the golden set. 30 fps or better on the lite tier. Share links bring new installs. |
| 3. Flywheel (v2) | Learned ranker, automated retraining with gates, second room type, direct brand deals, paid renders, flat-type library | Ranker beats rules in an A/B test. Revenue per design exceeds cost per design by a clear multiple. |

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Thin affiliate income | 1.5 to 8% with short windows may not cover acquisition | Direct deals, paid extras, re-engagement links |
| Catalog data quality | Wrong sizes break the core promise | Verified flag, range checks, "did it fit" loop |
| Android accuracy | Most of India; no depth hardware | Tape check on every scan, manual fallback, LiDAR-as-truth training |
| 3D asset quality | Ugly models kill desire to buy | Templates first, human check on hero items |
| Model licenses | Many research weights forbid commercial use | License review before any model enters the pipeline |
| Privacy | Videos of homes are sensitive | Clear consent, process on device where possible, blur faces and photos, delete raw video after reconstruction, comply with India's data protection law |
| Retailer terms | Programs can restrict apps or price display | Read terms early, keep more than one network |
| Rate changes | Commission cards change yearly | No single retailer above 40% of revenue |

Decisions:

- [x] Launch market and device priority: India, any phone, no dependence on device hardware.
- [x] Design direction: the LiveMap design system, premium and motion-rich on both Android and iOS.
- [ ] First room type: living room or bedroom.
- [ ] Team size and monthly budget.
- [ ] Any existing relationships with furniture or decor brands that could be first catalog partners.
- [ ] Revenue mix at launch: affiliate only, or affiliate plus paid renders.
- [ ] Final product name, after domain, app store and trademark checks.
