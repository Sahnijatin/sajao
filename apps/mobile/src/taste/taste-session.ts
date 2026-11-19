// The taste onboarding flow as one pure state machine: light context (age
// band, household, owned or rented), adaptive swipes, then budget and
// must-haves. The screen only renders this state and sends it events.
import type { Brief, TasteProfile } from "@sajao/schemas";
import {
  type AgeBand,
  type Answer,
  type Attributes,
  attributesFrom,
  type Belief,
  initialBelief,
  isDone,
  nextCard,
  plannedTotal,
  type Style,
  styleBlend,
  type Swipe,
  type SwipeCard,
  swipesReady,
  tasteSoFar,
  type Trait,
  updateBelief,
} from "./adaptive-swipes";

export type Household = TasteProfile["context"]["household"][number];
export type Tenure = TasteProfile["context"]["tenure"];
export type Flexibility = Brief["budget"]["flexibility"];

export const AGE_BANDS: readonly AgeBand[] = ["18_24", "25_34", "35_44", "45_54", "55_plus"];
export const HOUSEHOLDS: readonly Household[] = [
  "alone",
  "couple",
  "family_with_kids",
  "parents",
  "pets",
];
export const TENURES: readonly Tenure[] = ["owned", "rented"];
/** Budget choices in rupees. */
export const BUDGETS_INR: readonly number[] = [50_000, 100_000, 150_000, 250_000, 400_000];
export const MUST_HAVES = [
  "sofa",
  "bed",
  "rug",
  "lighting",
  "storage",
  "desk",
  "plants",
  "art",
] as const;
export type MustHave = (typeof MUST_HAVES)[number];

export type Step = "context" | "swipes" | "budget" | "done";

export interface TasteState {
  step: Step;
  ageBand: AgeBand | null;
  household: Household[];
  tenure: Tenure | null;
  belief: Belief;
  swipes: Swipe[];
  /** The card on screen during the swipes step. */
  card: SwipeCard | null;
  budgetInr: number | null;
  flexibility: Flexibility;
  mustHaves: MustHave[];
  considerVastu: boolean;
}

export function startTaste(): TasteState {
  return {
    step: "context",
    ageBand: null,
    household: [],
    tenure: null,
    belief: initialBelief(null),
    swipes: [],
    card: null,
    budgetInr: null,
    flexibility: "strict",
    mustHaves: [],
    considerVastu: false,
  };
}

export type TasteEvent =
  | { type: "ageBand"; value: AgeBand }
  | { type: "household"; value: Household }
  | { type: "tenure"; value: Tenure }
  | { type: "continue" }
  | { type: "answer"; value: Answer }
  | { type: "budget"; value: number }
  | { type: "flexibility"; value: Flexibility }
  | { type: "mustHave"; value: MustHave }
  | { type: "considerVastu"; value: boolean }
  | { type: "back" };

const toggle = <T>(list: T[], value: T): T[] =>
  list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

export function canContinue(state: TasteState): boolean {
  if (state.step === "context") {
    return state.ageBand !== null && state.household.length > 0 && state.tenure !== null;
  }
  if (state.step === "budget") return state.budgetInr !== null;
  return false;
}

export function tasteReducer(deck: readonly SwipeCard[]) {
  const seen = (state: TasteState) => new Set(state.swipes.map((swipe) => swipe.card_id));
  // No pictures for the cards yet: the swipes are left out.
  const withSwipes = swipesReady(deck);

  return (state: TasteState, event: TasteEvent): TasteState => {
    switch (event.type) {
      case "ageBand":
        // Before any swipe the age band reseeds the first guess; after that it has no effect.
        return state.swipes.length === 0
          ? { ...state, ageBand: event.value, belief: initialBelief(event.value) }
          : { ...state, ageBand: event.value };
      case "household":
        return { ...state, household: toggle(state.household, event.value) };
      case "tenure":
        return { ...state, tenure: event.value };
      case "budget":
        return { ...state, budgetInr: event.value };
      case "flexibility":
        return { ...state, flexibility: event.value };
      case "mustHave":
        return { ...state, mustHaves: toggle(state.mustHaves, event.value) };
      case "considerVastu":
        return { ...state, considerVastu: event.value };
      case "continue": {
        if (!canContinue(state)) return state;
        if (state.step === "budget") return { ...state, step: "done" };
        const done = !withSwipes || isDone(state.belief, state.swipes, deck.length);
        return done
          ? { ...state, step: "budget", card: null }
          : { ...state, step: "swipes", card: nextCard(state.belief, deck, seen(state)) };
      }
      case "answer": {
        if (state.step !== "swipes" || !state.card) return state;
        const belief = updateBelief(state.belief, state.card, event.value);
        const swipes = [...state.swipes, { card_id: state.card.id, answer: event.value }];
        const next = { ...state, belief, swipes };
        if (isDone(belief, swipes, deck.length)) return { ...next, step: "budget", card: null };
        return { ...next, card: nextCard(belief, deck, seen(next)) };
      }
      case "back": {
        if (state.step === "swipes") return { ...state, step: "context" };
        if (state.step === "budget") {
          if (!withSwipes) return { ...state, step: "context" };
          return { ...state, step: "swipes", card: nextCard(state.belief, deck, seen(state)) };
        }
        return state;
      }
    }
  };
}

export function progress(state: TasteState): { current: number; total: number } {
  return { current: state.swipes.length + 1, total: plannedTotal(state.swipes.length) };
}

export interface TasteAnswers {
  context: { age_band: AgeBand; household: Household[]; tenure: Tenure };
  swipes: { card_id: string; liked: boolean }[];
  attributes: Attributes;
  style_blend: { style: Style; weight: number }[];
  traits: Trait[];
  budget: { limit: { currency: "INR"; amount_minor: number }; flexibility: Flexibility };
  must_haves: MustHave[];
  consider_vastu: boolean;
}

/**
 * What the app sends when onboarding is finished. The server adds the taste
 * vector and builds the TasteProfile and the Brief from this.
 */
export function tasteAnswers(state: TasteState, deck: readonly SwipeCard[]): TasteAnswers {
  if (state.step !== "done" || !state.ageBand || !state.tenure || state.budgetInr === null) {
    throw new Error("Taste onboarding is not finished");
  }
  return {
    context: { age_band: state.ageBand, household: state.household, tenure: state.tenure },
    // "Not sure" is not a like or a dislike, so it is left out.
    swipes: state.swipes
      .filter((swipe) => swipe.answer !== "unsure")
      .map((swipe) => ({ card_id: swipe.card_id, liked: swipe.answer === "love" })),
    attributes: attributesFrom(state.swipes, deck),
    style_blend: styleBlend(state.belief),
    traits: tasteSoFar(state.swipes, deck),
    budget: {
      limit: { currency: "INR", amount_minor: state.budgetInr * 100 },
      flexibility: state.flexibility,
    },
    must_haves: state.mustHaves,
    consider_vastu: state.considerVastu,
  };
}
