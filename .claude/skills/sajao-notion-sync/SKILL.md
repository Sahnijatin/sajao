---
name: sajao-notion-sync
description: Use at the start and end of every Sajao work session, and whenever scope, a decision or a task status changes. Reads the current sprint from Notion, keeps tasks and PR links up to date, and runs the scope change protocol.
---

# Sajao Notion sync

Notion is the single tracker. Work that is not a task there does not start.

## Where things live

| What | Notion location |
| --- | --- |
| Hub page | https://app.notion.com/p/418ba1e3f4e581119b7fd1285f226f30 |
| Build charter | https://app.notion.com/p/418ba1e3f4e581a39120eb9ffc4bff15 |
| Sprints | collection://418ba1e3-f4e5-8181-b7ce-000b9c61c8cc |
| Tasks | collection://418ba1e3-f4e5-819c-8be8-000b17e77eb8 |
| Epics | collection://418ba1e3-f4e5-81ee-86bf-000b2afc9617 |
| Decisions | collection://418ba1e3-f4e5-81dc-99ca-000bb3f87136 |
| Scope changes | collection://418ba1e3-f4e5-8155-af79-000b75a4c2c8 |
| Bugs | collection://418ba1e3-f4e5-8131-99dc-000ba66e62df |
| Golden set | collection://418ba1e3-f4e5-8159-b664-000b711ffe1f |
| Catalog sources | collection://418ba1e3-f4e5-8128-80a5-000b956c609c |

Task fields: Name, Sprint, Epic, Owner (Claude Code, Cowork, Founder), Status (Backlog, Ready, In progress, In review, Blocked, Done), Priority (P0 to P2), Acceptance criteria, Non-negotiable, Size, PR.

## Session start

1. Find the sprint with Status "Active".
2. Query Tasks in that sprint for your owner (Claude Code or Cowork).
3. Pick the highest-priority task in "Ready" or "In progress". Read its acceptance criteria; they define done.
4. Set it to "In progress" before you begin.

## During work

- If you find needed work that no task covers, do not do it. Add a row to Scope changes (Proposal, Type, Impact on sprints, Reason, Raised on) with Status "Proposed", tell the founder, and continue with in-scope work.
- If a choice has real trade-offs, add a row to Decisions with options and a one-line reason. Founder decisions are marked "Founder"; routine engineering choices "Lead".
- If you are blocked, set the task to "Blocked" and say why in the task body.

## Session end

1. Put the PR URL in the task's PR field and set Status to "In review" (or "Done" once merged).
2. Add a short note to the task body: what changed, what is left.
3. Log bugs you found in Bugs.
4. When every task in the sprint is done, set the sprint to "Done" and the next sprint to "Active", after the founder confirms.

## Approved scope changes

Only after a Scope changes row is "Approved": create or edit the affected tasks, update the charter and repo docs, and log the decision.
