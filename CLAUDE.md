# Sajao

Android and iOS app: photos or a short video of a room in, three redesigns built from real, buyable products that fit, out. Tagline: "Scan your room. See it redone. Buy what fits." The founder approves scope; you lead execution as CTO and product lead.

## Every session

1. Load the `sajao-notion-sync` skill. Read the active sprint in Notion, pick your task, set it to "In progress".
2. Load the `sajao-guardrails` skill before designing or reviewing any change, and again before opening a PR.
3. End by linking the PR in the Notion task, updating status and notes.

## Sources of truth

- Notion "Sajao" hub: the only tracker (sprints, tasks, decisions, scope changes, bugs, golden set, catalog sources). The approved build charter lives there.
- `docs/`: product and engineering documentation, kept in sync with the charter. `ENGINEERING.md`: rules every change follows.
- `packages/schemas`: the contract between app, API and workers.

## Three non-negotiables

1. Visual quality: the redesigned room must genuinely excite the user.
2. Spatial credibility: dimensions and furniture make sense; every design passes the verifier.
3. Commercial utility: every item is a real, in-stock product with a price and a working link.

All three are rendered from one `Design` object. Never build them as separate features.

## Rules

- No scope change without an approved row in Notion "Scope changes". Propose, then wait.
- Generative models never set a dimension, position or price. Geometry models estimate; tape verifies; code decides fit.
- Validate every model output. Every model call goes through the model gateway with fallbacks and caps.
- Design quality from day one: theme package, motion and haptics on every screen; test on the budget Android.
- Production grade from the start: stateless services, durable idempotent jobs, migrations in the repo, secrets only in secret managers.
- Think from first principles; prefer the simplest design that meets the gate; measure before claiming.
- Small PRs, one task each, tests passing. Log trade-offs in Notion "Decisions".

## Writing and repo hygiene

- No em dashes. Use "license". Concise and actionable. Gender-neutral copy ("you", "your", "they").
- No personal names in product text, code, commits or PRs. Never name the Vastu consultant.
- No mention of AI coding tools, assistants or co-author trailers in commits, PRs or docs.
- No paywall, lock or upgrade prompt in the app until the founder switches entitlements on.
- No calendar dates in repo docs; dates live in Notion.
- `python scripts/check_docs.py` must pass.

## Skills in this repo

`.claude/skills/` holds our two skills and vendored, MIT-licensed third-party skills (Expo, React Native, Supabase, Karpathy guidelines). Sources and licenses are in `.claude/skills/THIRD_PARTY_NOTICES.md`.
