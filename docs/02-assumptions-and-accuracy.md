# Assumptions and the honest limit on accuracy

Zero error from a phone camera is not physically achievable. What is achievable is a known error band, shown to the user, and a system that never makes a fit claim it cannot back.

Working assumptions (changing any of these shifts the design):

- India first, consumer app, affiliate-led revenue.
- One room per project. Whole-home comes later.
- Small founding team, lean budget, building with AI coding tools.
- Two ideas are kept from the first rough vision draft: reuse existing models, and keep code, not an LLM, as the authority on measurements.

How "no room for error" becomes an engineering rule:

| Rule | What it means in the product |
| --- | --- |
| Every number carries a source | Each dimension is tagged measured, user-confirmed or estimated. Only the first two can back a "this fits" claim. |
| Fit uses a safety margin | If the scan's error band is 3 cm, an item must clear by more than 3 cm. Otherwise the app says "tight fit, please measure this wall". |
| Ask instead of guess | When confidence is low, the app asks for one tape measurement. One confirmed length fixes the scale of the whole room. |
| Nothing unverified ships | A separate checker re-tests every design for collisions, clearances, budget and stock before she sees it. |

Accuracy targets to validate in a benchmark, not promises: wall lengths within about 2 to 3% on any phone after one tape measurement, about 1% after two, and 1 to 3 cm on LiDAR devices.
