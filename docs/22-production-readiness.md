# Production readiness

The gaps a careful team closes from day one. Each item is a task in Notion in the sprint where it fits.

| Area | What we do |
| --- | --- |
| Environments | Separate dev, staging and production (Supabase projects, Modal apps, EAS channels); config and migrations in the repo |
| API contract | Versioned `/v1` API; OpenAPI generated from FastAPI; typed TypeScript client generated from it; minimum app version enforced so old apps can be told to update |
| Database discipline | Migrations only through the repo; backward-compatible changes (expand, then contract); daily backups and point-in-time recovery on production |
| Releases | GitHub Actions CI; EAS Build; EAS Update for over-the-air JavaScript fixes with instant rollback; phased store rollouts; feature flags in PostHog |
| Observability | Sentry on app and API; structured logs and traces across API, workers and model calls; dashboards for cost per room, latency per step, error rates; alerts to the founder |
| Security | Secrets only in managed secret stores; signed URLs for photos; dependency and secret scanning in CI; prompt-injection guards on any user text or image sent to models |
| Upload safety | Reject non-room or explicit images with a classifier; blur faces and personal photos before storage |
| Privacy | Clear consent at first use; in-app account and data deletion (required by both stores); data retention rules; raw video deleted after processing |
| AI quality operations | Prompts and model versions pinned in the repo; every model output logged for audit; golden-set evaluations rerun on any model or prompt change |
| Language and units | English and Hindi from day one (all strings externalised); dimensions in feet and inches or centimetres by user choice; INR formatting |
| Growth plumbing | Deep links and universal links for shared designs; landing page for people without the app (web viewer after launch); referral source tracked |
| Analytics plan | Event plan defined before screens are built: capture started, room ready, taste done, designs viewed, swap, buy tap, share |
| Internal admin | One web admin for catalog curation, user support, flags and cost dashboard |
| Support | In-app feedback with logs attached, support email, FAQ |
| Testing | Unit and property tests; API contract tests; end-to-end flows on real devices; device farm runs; visual checks on key screens |
