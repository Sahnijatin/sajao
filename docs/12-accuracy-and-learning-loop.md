# Accuracy and the self-improving loop

The system retrains itself automatically, but through a gated pipeline, not by changing its own weights live. A model that updates itself in production with no test is how accuracy gets worse without anyone noticing.

Three different things can be wrong, and each gets its own signal and its own loop:

| Layer | How it goes wrong | Free signal from users | What retrains | How often |
| --- | --- | --- | --- | --- |
| Geometry | Wrong scale, missed door or window | Confirmed measurements, floor-plan corrections, LiDAR scans compared with the camera-only path | Scale correction and layout models | Monthly |
| Object detection | Sofa labelled as a bed | Label fixes on the confirm screen | Detector fine-tune | Monthly |
| Product data | Listed size is wrong | "Did it fit?" follow-up, returns, reports | Validation rules, verified flag | Continuous |
| Layout taste | Layout is valid but she moves things | The difference between our layout and her final one | Soft-score weights in the solver | Weekly |
| Product taste | Wrong style or price feel | Swaps, saves, clicks, purchases, which variation won | Ranking model | Nightly |

The automatic pipeline: events land in a log; a scheduled job trains a candidate model; the candidate is scored on a fixed golden set and on replayed history; it then runs in shadow, then on 5% of traffic; it is promoted if it wins and rolled back if it loses. No human is needed unless a gate fails.

Rules that keep it accurate everywhere, not only on rooms it has seen:

- **Learning touches taste, never truth.** Models may reorder and re-weight. They cannot change hard rules or the verifier. A bad model can make a design less attractive, never one that does not fit.
- **Judge by the worst slice.** The golden set is split by room type, size, lighting, device tier and city. A model ships only if no slice gets worse. Averages hide failures.
- **Send uncertainty to people.** Low-confidence scans go to a small human review queue. Their fixes become the most valuable training labels.
- **Explore on purpose.** About 10% of product slots show less-proven items, so the ranker does not lock onto early favourites.
- **Build the golden set first.** Tape-measure 50 real rooms across device tiers before launch. Without ground truth, "accurate" has no meaning.

Cold start, before any user data exists: have an interior designer encode the rules and about 200 reference looks, and use open synthetic room datasets (check their licenses) to stress-test the solver.
