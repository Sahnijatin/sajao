# Engineering process

## Tracking

Notion is the single tracker. Sprints, epics, tasks, decisions, scope changes, bugs, the golden set and catalog sources all live there. Dates live there too, never in repo docs.

1. Anything not in an approved task is out of scope by default.
2. A needed change becomes a row in "Scope changes" with its impact, and work on it stops until the founder approves.
3. Only after approval are tasks, sprints, the decision log and repo docs updated.
4. Each work session starts by reading the active sprint and ends by updating task status, PR links and notes.

The repo skill `.claude/skills/sajao-notion-sync` holds the database locations and the exact steps.

## Work split

| In the repo | Desktop, browser, docs | Founder |
| --- | --- | --- |
| App code, backend, pipelines, schemas, migrations | Notion upkeep: sprints, tasks, decisions | Approves scope, scope changes and screen designs |
| Tests, CI, build configs | Screen mockups before coding | Accounts, keys, payments, store submissions |
| Model gateway, prompt files, eval scripts | Brand and affiliate research, sign-up forms | Brand calls and direct deals |
| Catalog ingestion and curation tool | Curation reviews and blind render votes | Tape-measuring golden rooms, device testing |
| Pull requests; repo docs kept in sync | Store copy, privacy policy, terms, disclosures | Recruiting testers |
| Performance and device fixes | Competitor teardowns, launch plan | Vastu consultant review |

Anything that ends in a commit is done in the repo; anything that ends in a document, spreadsheet, browser action or decision is done outside it. Neither side adds scope without an approved scope change.

## Working rules

1. **Contracts first.** Schemas in `packages/schemas`; schema changes are their own reviewed change.
2. **Screens are designed before they are coded** and approved by the founder.
3. **Small pull requests,** one task each, tests passing, linked from the Notion task.
4. **Evaluation in three tiers** as defined in [AI models and evaluation](11-ai-models-and-evaluation.md). Only the fast tier blocks merges.
5. **Decision log with reasons.** Every "chose X over Y" gets one line in Notion "Decisions" and, for lasting architecture choices, in the roadmap doc.
6. **Measure before claiming.** Targets stay targets until the golden set measures them.
7. **Observability from the first build.** Crashes, analytics, cost and latency per step, gateway logs.
8. **Feature flags** for entitlements, new models and risky features.

## Repo guardrails

`CLAUDE.md` and `.claude/skills/` hold the rules every coding session loads: the `sajao-guardrails` checklist, the Notion sync steps, and vendored third-party skills (listed with licenses in `.claude/skills/THIRD_PARTY_NOTICES.md`). CI checks docs for hygiene rules.

## Device matrix

A recent iPhone, an older iPhone, a mid-range Android with ARCore, and a budget Android with 3 to 4 GB RAM that is not on ARCore's supported list. Every screen must work on the budget Android.

## Release flow

Internal builds on the device matrix, then the Play closed test (a personal developer account needs at least 12 opted-in testers for 14 continuous days before production access) and TestFlight, then store submission. Phased rollouts, EAS Update for over-the-air fixes with instant rollback.
