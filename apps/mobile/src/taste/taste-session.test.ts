import { MAX_SWIPES, MIN_SWIPES } from "./adaptive-swipes";
import { DECK } from "./deck";
import {
  canContinue,
  progress,
  startTaste,
  tasteAnswers,
  type TasteEvent,
  tasteReducer,
  type TasteState,
} from "./taste-session";

const reduce = tasteReducer(DECK);
const run = (state: TasteState, events: TasteEvent[]) => events.reduce(reduce, state);

const context: TasteEvent[] = [
  { type: "ageBand", value: "25_34" },
  { type: "household", value: "couple" },
  { type: "household", value: "pets" },
  { type: "tenure", value: "rented" },
  { type: "continue" },
];

/** Answer every card as someone who loves low clutter. */
function swipeAll(state: TasteState): TasteState {
  let current = state;
  while (current.step === "swipes") {
    const loves = current.card!.traits.includes("low_clutter");
    current = reduce(current, { type: "answer", value: loves ? "love" : "no" });
  }
  return current;
}

describe("taste onboarding flow", () => {
  it("needs age band, household and owned or rented before the swipes", () => {
    let state = startTaste();
    expect(canContinue(state)).toBe(false);
    state = reduce(state, { type: "continue" });
    expect(state.step).toBe("context");
    state = run(state, context.slice(0, 2));
    expect(canContinue(state)).toBe(false);
    state = run(state, context.slice(2));
    expect(state.step).toBe("swipes");
    expect(state.card).not.toBeNull();
    expect(state.household).toEqual(["couple", "pets"]);
  });

  it("lets a household choice be tapped off again", () => {
    const state = run(startTaste(), [
      { type: "household", value: "couple" },
      { type: "household", value: "couple" },
    ]);
    expect(state.household).toEqual([]);
  });

  it("shows 8 to 12 cards, never the same one twice, then moves to budget", () => {
    const state = swipeAll(run(startTaste(), context));
    expect(state.step).toBe("budget");
    expect(state.swipes.length).toBeGreaterThanOrEqual(MIN_SWIPES);
    expect(state.swipes.length).toBeLessThanOrEqual(MAX_SWIPES);
    expect(new Set(state.swipes.map((swipe) => swipe.card_id)).size).toBe(state.swipes.length);
  });

  it("counts progress as on the mockup: 1 of 10 at the start", () => {
    let state = run(startTaste(), context);
    expect(progress(state)).toEqual({ current: 1, total: 10 });
    state = run(state, Array(3).fill({ type: "answer", value: "unsure" }));
    expect(progress(state)).toEqual({ current: 4, total: 10 });
  });

  it("ignores answers outside the swipes step", () => {
    const state = reduce(startTaste(), { type: "answer", value: "love" });
    expect(state.swipes).toEqual([]);
  });

  it("goes back without losing swipes", () => {
    let state = run(startTaste(), context);
    state = run(state, [
      { type: "answer", value: "love" },
      { type: "answer", value: "no" },
      { type: "back" },
    ]);
    expect(state.step).toBe("context");
    expect(state.swipes).toHaveLength(2);
    state = reduce(state, { type: "continue" });
    expect(state.step).toBe("swipes");
    expect(state.swipes.map((swipe) => swipe.card_id)).not.toContain(state.card!.id);
  });

  it("does not let the age band rewrite what the swipes have learned", () => {
    let state = run(startTaste(), context);
    state = reduce(state, { type: "answer", value: "love" });
    const learned = state.belief;
    state = reduce(state, { type: "ageBand", value: "55_plus" });
    expect(state.belief).toBe(learned);
  });

  it("needs a budget to finish, and defaults to a strict one", () => {
    let state = swipeAll(run(startTaste(), context));
    expect(canContinue(state)).toBe(false);
    expect(reduce(state, { type: "continue" }).step).toBe("budget");
    expect(state.flexibility).toBe("strict");
    state = run(state, [{ type: "budget", value: 150_000 }, { type: "continue" }]);
    expect(state.step).toBe("done");
  });

  it("produces the answers the server needs, with money in paise", () => {
    const done = run(swipeAll(run(startTaste(), context)), [
      { type: "budget", value: 150_000 },
      { type: "flexibility", value: "stretch_10" },
      { type: "mustHave", value: "sofa" },
      { type: "mustHave", value: "rug" },
      { type: "considerVastu", value: true },
      { type: "continue" },
    ]);
    const answers = tasteAnswers(done, DECK);
    expect(answers.context).toEqual({
      age_band: "25_34",
      household: ["couple", "pets"],
      tenure: "rented",
    });
    expect(answers.budget).toEqual({
      limit: { currency: "INR", amount_minor: 15_000_000 },
      flexibility: "stretch_10",
    });
    expect(answers.must_haves).toEqual(["sofa", "rug"]);
    expect(answers.consider_vastu).toBe(true);
    expect(answers.traits).toContain("low_clutter");
    expect(answers.style_blend[0]!.weight).toBeGreaterThan(0);
    expect(answers.swipes.every((swipe) => typeof swipe.liked === "boolean")).toBe(true);
  });

  it("leaves Not sure answers out of the likes and dislikes", () => {
    let state = run(startTaste(), context);
    while (state.step === "swipes") state = reduce(state, { type: "answer", value: "unsure" });
    state = run(state, [{ type: "budget", value: 50_000 }, { type: "continue" }]);
    expect(tasteAnswers(state, DECK).swipes).toEqual([]);
  });

  it("refuses to produce answers before onboarding is finished", () => {
    expect(() => tasteAnswers(startTaste(), DECK)).toThrow();
  });
});
