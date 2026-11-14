---
name: sajao-guardrails
description: Use before designing, writing or reviewing any Sajao change (code, schema, prompt, doc or PR). Checks the three non-negotiables, the Design object contract, the scope protocol, and the writing and hygiene rules.
---

# Sajao guardrails

Run this checklist before you start a change and again before you open the PR. If any answer is "no", fix it or stop and raise it.

## 1. Is this in scope?

- The work matches a Notion task in the current sprint (see the `sajao-notion-sync` skill).
- Nothing beyond that task's acceptance criteria is added. Anything extra becomes a row in Notion "Scope changes" and waits for founder approval.
- Deep before wide: finish the current tier before starting the next.

## 2. The three non-negotiables

Every change must keep all three true, and they are never built as separate features:

1. **Visual quality.** The redesigned room must genuinely excite the user. No render reaches a user without passing structure, likeness and aesthetic checks.
2. **Spatial credibility.** Dimensions and furniture make sense. Every design passes the verifier. Every dimension carries a value, a source (measured, estimated, user-confirmed) and an error band; the solver uses the band as margin.
3. **Commercial utility.** Every item is a real, in-stock product with a price and a working buy or rent link. Totals come from the same list the render shows.

All three are derived from one `Design` object (schemas in `packages/schemas`). The render, the plan and the shopping list are views of it. If your change lets any of them disagree, it is wrong.

## 3. Truth rules

- Generative models never set a dimension, position, price or stock value. Geometry models estimate; tape verifies; code decides fit.
- Every model output is validated: schema for text, geometry for layouts, structure and likeness for images.
- Every model call goes through the model gateway with fallbacks, caps and logging. The app degrades, it never stops suddenly.
- Prompts and model versions are pinned in the repo. Changing either reruns the golden-set evaluations.

## 4. Engineering rules

- Schemas are the contract; validate at every boundary. Schema changes are their own reviewed change.
- Small PRs, one task each, tests passing. Solver, verifier and relaxation order are pure, deterministic and property-tested.
- Every write endpoint accepts an idempotency key. Expensive endpoints require app attestation and respect spend caps.
- Database changes are backward compatible (expand, then contract) and go only through migrations in the repo.
- Every screen uses the theme package, motion presets and haptic map, respects reduced motion and works on the budget Android.
- Strings are externalised (English and Hindi). Dimensions show in cm or feet and inches by user choice. Prices in INR.
- Secrets never enter the repository, logs or chat.

## 5. Writing and hygiene

- No em dashes anywhere. Use "license" (not "licence"). Concise and plain.
- No personal names in product text, code, commits, PRs or docs. Never name the Vastu consultant.
- Gender-neutral copy: "you", "your", "they", never "her" or "his" for the user.
- No mention of AI coding tools, assistants or co-author trailers in commits, PRs or product docs.
- No paywall, lock, upgrade prompt or paid badge in the app until the founder switches entitlements on.
- No calendar dates in repo docs; dates live in Notion.

## 6. Before you say "done"

- Run the tests and checks; read the output; quote what passed.
- Link the PR in the Notion task and move it to "In review".
- Log any choice with trade-offs in Notion "Decisions" with a one-line reason.
