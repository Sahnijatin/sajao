# Engineering process

How the build is run so quality holds as it grows.

1. **Contracts first.** JSON schemas for the room, product, brief and design live in `packages/schemas` and are versioned. App, API and engine validate against them. A schema change is its own reviewed change.
2. **Golden set from the first week.** 10 to 20 real rooms, tape-measured, each scanned on the device matrix. It grows toward 50 before launch, weighted to typical Indian flats.
3. **Evaluation runs on every change.** The suite in [AI models and evaluation](11-ai-models-and-evaluation.md) runs in CI. Any slice getting worse blocks the change.
4. **Decision log.** Every "chose X over Y" goes into the table in [roadmap, risks and decisions](16-roadmap-risks-decisions.md) with one line of reason.
5. **Small branches.** One feature per branch, merged when tests pass. No long-lived branches.
6. **Tests where it matters.** The solver and verifier get property tests (random rooms and items: the verifier must catch every planted violation). Schemas get round-trip tests. Capture gets the benchmark.
7. **Device matrix.** iPhone 17 Pro (LiDAR and RoomPlan), iPhone 16, iPhone 13, a mid-range ARCore Android, and an old budget Android not on ARCore's supported list (3 to 4 GB RAM). Every capture or rendering change is tried on the budget Android.
8. **Observability from the first build.** Crash reporting, product analytics, cost per room per step, and model call logs through the gateway.
9. **Cost guardrails.** Per-user daily caps, spend alerts, automatic soft limit.
10. **Feature switches.** Entitlements, new models and risky features ship behind remote switches.
11. **Privacy by default.** Raw video deleted after reconstruction; faces and personal photos blurred in anything stored; consent before any data is used for training.
12. **Rules file.** [ENGINEERING.md](../ENGINEERING.md) holds the hard rules every change follows.

## Release flow

Internal builds go to the device matrix, then a closed beta, then the stores. On Google Play, a personal developer account created after November 2023 must run a closed test with at least 12 opted-in testers for 14 continuous days before production access; plan the beta to cover it.
