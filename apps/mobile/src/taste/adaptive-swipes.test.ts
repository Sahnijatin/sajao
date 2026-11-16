import {
  type Answer,
  attributesFrom,
  type Belief,
  entropy,
  expectedGain,
  initialBelief,
  isDone,
  MAX_SWIPES,
  MIN_SWIPES,
  nextCard,
  plannedTotal,
  type Style,
  styleBlend,
  STYLES,
  type Swipe,
  tasteSoFar,
  updateBelief,
} from "./adaptive-swipes";
import { DECK } from "./deck";

const sum = (belief: Belief) => STYLES.reduce((total, style) => total + belief[style], 0);
const top = (belief: Belief) => [...STYLES].sort((a, b) => belief[b] - belief[a])[0]!;

/** Someone who truly loves one style, answering every card honestly. */
function persona(style: Style) {
  return (cardId: string): Answer =>
    DECK.find((card) => card.id === cardId)!.appeal[style] >= 0.5 ? "love" : "no";
}

function runSession(
  answer: (cardId: string) => Answer,
  ageBand: Parameters<typeof initialBelief>[0] = null,
) {
  let belief = initialBelief(ageBand);
  const swipes: Swipe[] = [];
  const seen = new Set<string>();
  while (!isDone(belief, swipes, DECK.length)) {
    const card = nextCard(belief, DECK, seen)!;
    const given = answer(card.id);
    belief = updateBelief(belief, card, given);
    swipes.push({ card_id: card.id, answer: given });
    seen.add(card.id);
  }
  return { belief, swipes };
}

describe("the deck", () => {
  it("has three cards for each of the six styles, with unique ids", () => {
    expect(new Set(DECK.map((card) => card.id)).size).toBe(18);
    for (const style of STYLES) {
      expect(DECK.filter((card) => card.appeal[style] === 0.9)).toHaveLength(3);
    }
  });

  it("keeps every value between 0 and 1", () => {
    for (const card of DECK) {
      for (const value of [...Object.values(card.appeal), ...Object.values(card.attributes)]) {
        expect(value).toBeGreaterThanOrEqual(0);
        expect(value).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("belief about styles", () => {
  it("starts even when nothing is known", () => {
    const belief = initialBelief(null);
    expect(sum(belief)).toBeCloseTo(1);
    expect(new Set(STYLES.map((style) => belief[style].toFixed(6))).size).toBe(1);
  });

  it("uses the age band only as a weak first guess", () => {
    for (const band of ["18_24", "25_34", "35_44", "45_54", "55_plus"] as const) {
      const belief = initialBelief(band);
      expect(sum(belief)).toBeCloseTo(1);
      // No style starts above a quarter or is ruled out.
      for (const style of STYLES) {
        expect(belief[style]).toBeLessThan(0.25);
        expect(belief[style]).toBeGreaterThan(0.1);
      }
    }
  });

  it("lets your own choices override the age guess within a few swipes", () => {
    // The 55 plus guess leans away from maximalism; this person loves it.
    const { belief } = runSession(persona("warm_maximalist"), "55_plus");
    expect(top(belief)).toBe("warm_maximalist");
  });

  it("raises a style when its card is loved and lowers it when rejected", () => {
    const card = DECK.find((c) => c.id === "japandi-low-sofa")!;
    const start = initialBelief(null);
    expect(updateBelief(start, card, "love").japandi).toBeGreaterThan(start.japandi);
    expect(updateBelief(start, card, "no").japandi).toBeLessThan(start.japandi);
    expect(sum(updateBelief(start, card, "love"))).toBeCloseTo(1);
  });

  it("does not change on Not sure", () => {
    const start = initialBelief(null);
    expect(updateBelief(start, DECK[0]!, "unsure")).toBe(start);
  });

  it("never rules a style out on one swipe", () => {
    let belief = initialBelief(null);
    for (const card of DECK.filter((c) => c.appeal.japandi === 0.9)) {
      belief = updateBelief(belief, card, "no");
    }
    expect(belief.japandi).toBeGreaterThan(0);
  });
});

describe("choosing the next card", () => {
  it("picks the card expected to teach the most", () => {
    const belief = initialBelief(null);
    const chosen = nextCard(belief, DECK, new Set())!;
    const best = Math.max(...DECK.map((card) => expectedGain(belief, card)));
    expect(expectedGain(belief, chosen)).toBeCloseTo(best);
    expect(best).toBeGreaterThan(0);
  });

  it("never repeats a card and returns nothing when the deck is used up", () => {
    const seen = new Set(DECK.slice(0, 17).map((card) => card.id));
    expect(nextCard(initialBelief(null), DECK, seen)!.id).toBe(DECK[17]!.id);
    seen.add(DECK[17]!.id);
    expect(nextCard(initialBelief(null), DECK, seen)).toBeNull();
  });

  it("stops asking about a style it is already sure of", () => {
    // Certain it is Japandi versus wabi-sabi: cards that split those two matter most.
    const belief = { ...initialBelief(null) };
    for (const style of STYLES) belief[style] = 0.01;
    belief.japandi = 0.48;
    belief.minimal_wabi_sabi = 0.48;
    const chosen = nextCard(belief, DECK, new Set())!;
    expect(Math.abs(chosen.appeal.japandi - chosen.appeal.minimal_wabi_sabi)).toBeGreaterThan(0.3);
  });

  it("is deterministic", () => {
    const a = runSession(persona("japandi"));
    const b = runSession(persona("japandi"));
    expect(a.swipes).toEqual(b.swipes);
  });

  it("learns more per swipe than showing cards in deck order", () => {
    const answer = persona("eclectic_retro");
    const adaptive = runSession(answer);
    let ordered = initialBelief(null);
    for (const card of DECK.slice(0, adaptive.swipes.length)) {
      ordered = updateBelief(ordered, card, answer(card.id));
    }
    expect(entropy(adaptive.belief)).toBeLessThan(entropy(ordered));
  });
});

describe("a whole session", () => {
  it.each(STYLES)("finds a %s lover in 8 to 12 swipes", (style) => {
    const { belief, swipes } = runSession(persona(style));
    expect(swipes.length).toBeGreaterThanOrEqual(MIN_SWIPES);
    expect(swipes.length).toBeLessThanOrEqual(MAX_SWIPES);
    expect(top(belief)).toBe(style);
    expect(styleBlend(belief)[0]!.style).toBe(style);
  });

  it("never stops before 8 swipes, and always stops by 12", () => {
    const sure = { ...initialBelief(null), japandi: 0.99 };
    const swipes = (n: number): Swipe[] => Array(n).fill({ card_id: "x", answer: "love" });
    expect(isDone(sure, swipes(7), DECK.length)).toBe(false);
    expect(isDone(sure, swipes(8), DECK.length)).toBe(true);
    expect(isDone(initialBelief(null), swipes(11), DECK.length)).toBe(false);
    expect(isDone(initialBelief(null), swipes(12), DECK.length)).toBe(true);
  });

  it("still finishes for someone who is never sure", () => {
    const { swipes, belief } = runSession(() => "unsure");
    expect(swipes).toHaveLength(MAX_SWIPES);
    expect(sum(belief)).toBeCloseTo(1);
  });

  it("shows a steady count: 10 planned, 12 once it runs longer", () => {
    expect([0, 3, 9].map(plannedTotal)).toEqual([10, 10, 10]);
    expect([10, 11].map(plannedTotal)).toEqual([12, 12]);
  });
});

describe("what the swipes say", () => {
  it("describes the taste as a blend that adds up to 1", () => {
    const { belief } = runSession(persona("japandi"));
    const blend = styleBlend(belief);
    expect(blend.reduce((total, entry) => total + entry.weight, 0)).toBeCloseTo(1, 1);
    expect(blend.every((entry) => entry.weight >= 0.1)).toBe(true);
    expect(blend.length).toBeLessThanOrEqual(6);
    const weights = blend.map((entry) => entry.weight);
    expect(weights).toEqual([...weights].sort((a, b) => b - a));
  });

  it("lists traits you keep choosing, and none you keep rejecting", () => {
    const { swipes } = runSession(persona("japandi"));
    const traits = tasteSoFar(swipes, DECK);
    expect(traits.length).toBeLessThanOrEqual(4);
    expect(traits).toEqual(expect.arrayContaining(["low_clutter", "natural_wood"]));
    expect(traits).not.toContain("pattern");
  });

  it("has nothing to say before any swipe", () => {
    expect(tasteSoFar([], DECK)).toEqual([]);
  });

  it("moves readable attributes toward what you love and away from what you reject", () => {
    const calm = attributesFrom(runSession(persona("minimal_wabi_sabi")).swipes, DECK);
    const loud = attributesFrom(runSession(persona("warm_maximalist")).swipes, DECK);
    expect(calm.boldness).toBeLessThan(0.5);
    expect(loud.boldness).toBeGreaterThan(0.5);
    expect(calm.clutter_tolerance).toBeLessThan(loud.clutter_tolerance);
    for (const value of [...Object.values(calm), ...Object.values(loud)]) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(1);
    }
  });

  it("stays neutral with no swipes or only Not sure", () => {
    const neutral = attributesFrom([], DECK);
    expect(Object.values(neutral).every((value) => value === 0.5)).toBe(true);
    expect(attributesFrom([{ card_id: DECK[0]!.id, answer: "unsure" }], DECK)).toEqual(neutral);
  });
});
