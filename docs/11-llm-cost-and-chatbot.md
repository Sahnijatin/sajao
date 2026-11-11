# LLM cost strategy and the chatbot

Keep the LLM out of the main loop and its cost stays under 1 rupee per design. The chatbot is a remote control for the solver, not a designer.

| Job | Done by | LLM cost |
| --- | --- | --- |
| Measuring the room | Camera capture, vision models and the tape check | None |
| Choosing and placing products | Vector search, solver, ranker | None |
| Explaining a design | Templates from solver scores | None |
| Reading the brief's free text | Small LLM, one call, JSON out | About 0.5 rupees or less |
| Common chat requests ("cheaper", "swap the sofa", "warmer") | Intent matcher, no LLM | None |
| Unusual chat requests | Small LLM with tool calls | About 0.5 rupees per message |
| Product attribute extraction | Small LLM, offline batch, once per product | One-time, cached |

The per-call figure assumes about 2,500 input and 600 output tokens at small-model prices of roughly $1 and $5 per million tokens. Treat it as approximate and check current pricing.

How the chatbot stays cheap and accurate:

- **Tools, not prose.** The model can only call functions: `swap_item`, `move_item`, `set_budget`, `change_palette`, `lock_item`, `regenerate`, `explain`. Every call passes through the same solver and verifier, so chat cannot produce an invalid room.
- **Small context.** Send a 300-token summary of the scene, not the whole scene graph.
- **Prompt caching** for the fixed system prompt and tool definitions.
- **A router first.** Around 20 intents cover most messages and need no model at all.
- **Limits.** Message caps per user per day on the free tier.
- **One gateway.** All calls go through a single internal service, so the provider or model can be changed in one place.

Later, once there are tens of thousands of logged brief-to-spec pairs, fine-tune a small open model with LoRA and self-host it. Do this only when monthly API spend exceeds the cost of running a GPU.
