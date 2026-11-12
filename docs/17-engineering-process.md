# Engineering process

The process is set up before any product code is written.

## Before the first line of product code

- [ ] Branch protection on `main`: changes arrive through pull requests; fast-tier CI must pass.
- [ ] CI running the fast tier (schemas, solver and verifier property tests, relaxation order, fixed-room design tests, Vastu cases).
- [ ] Schemas for room, product, brief and design in `packages/schemas`.
- [ ] Device matrix in hand: iPhone 17 Pro (LiDAR), iPhone 16, iPhone 13, a mid-range ARCore Android, an old budget Android not on ARCore's supported list (3 to 4 GB RAM).

## Working rules

1. **Build to the cut line.** Only the current tier in [principles and scope](01-bottom-line.md). Deep before wide.
2. **Contracts first.** Schema changes are their own reviewed change.
3. **Golden set grows weekly** toward 50 rooms, weighted to typical Indian flats.
4. **Evaluation in three tiers** as defined in [AI models and evaluation](11-ai-models-and-evaluation.md). Only the fast tier blocks merges; nightly regressions are reviewed with confidence intervals.
5. **Decision log with reasons.** Every "chose X over Y" gets one line of reason in the roadmap doc.
6. **Small pull requests.** One feature per branch.
7. **Unvalidated claims stay marked** until phase 0 data replaces them with measured numbers.
8. **Observability from the first build:** crashes, analytics, cost and latency per step, gateway logs.
9. **Cost guardrails:** per-user caps, spend alerts, fallback chain tested monthly.
10. **Feature switches** for entitlements, new models and risky features.
11. **Privacy by default:** raw video deleted after processing, blurring, consent before training use.
12. **Permissions log:** every brand and creator source and the permission covering it.

## Release flow

Internal builds on the device matrix, then closed beta, then stores. On Google Play, a personal developer account created after November 2023 needs a closed test with at least 12 opted-in testers for 14 continuous days before production access.
