// Adaptive taste swipes. Each next card is the one expected to tell us most
// about which styles you like, so 8 to 12 swipes learn more than 30 random
// ones. Plain probability, computed on the phone: no model call.
import type { TasteProfile } from "@sajao/schemas";

export type Style = TasteProfile["style_blend"][number]["style"];
export type AgeBand = TasteProfile["context"]["age_band"];

export const STYLES: readonly Style[] = [
  "modern_indian",
  "warm_luxe",
  "japandi",
  "warm_maximalist",
  "eclectic_retro",
  "minimal_wabi_sabi",
];

export type Answer = "love" | "no" | "unsure";

/** Readable traits a card can show, used for "Your taste so far". */
export type Trait =
  | "warm_tones"
  | "cool_tones"
  | "natural_wood"
  | "low_clutter"
  | "layered"
  | "bold_colour"
  | "soft_neutrals"
  | "brass"
  | "pattern"
  | "handmade"
  | "vintage"
  | "plants";

export interface SwipeCard {
  id: string;
  /** How strongly someone who likes each style would like this card, 0 to 1. */
  appeal: Record<Style, number>;
  traits: readonly Trait[];
  /** Where the card sits on each readable attribute, 0 to 1. */
  attributes: Attributes;
}

export interface Attributes {
  palette_warmth: number;
  saturation: number;
  boldness: number;
  clutter_tolerance: number;
  formality: number;
  trend_vs_timeless: number;
}

export type Belief = Record<Style, number>;

export const MIN_SWIPES = 8;
export const MAX_SWIPES = 12;
/** Stop early once one style is this likely, or the top two clearly lead. */
const CONFIDENT = 0.6;
const TOP_TWO_CONFIDENT = 0.85;

const normalise = (belief: Belief): Belief => {
  const total = STYLES.reduce((sum, style) => sum + belief[style], 0);
  const out = {} as Belief;
  for (const style of STYLES) out[style] = total > 0 ? belief[style] / total : 1 / STYLES.length;
  return out;
};

const uniform = (): Belief => normalise(Object.fromEntries(STYLES.map((s) => [s, 1])) as Belief);

/**
 * The age band only seeds the first guess, weakly: younger bands lean a
 * little toward expressive looks, older ones toward subtle, durable ones.
 * It never filters anything and is never shown back. A few swipes outweigh it.
 */
const AGE_LEAN: Record<AgeBand, Partial<Record<Style, number>>> = {
  "18_24": { eclectic_retro: 1, warm_maximalist: 1 },
  "25_34": { japandi: 1, eclectic_retro: 1 },
  "35_44": { modern_indian: 1, warm_luxe: 1 },
  "45_54": { warm_luxe: 1, modern_indian: 1 },
  "55_plus": { minimal_wabi_sabi: 1, modern_indian: 1 },
};
const AGE_PRIOR_WEIGHT = 0.15;

export function initialBelief(ageBand: AgeBand | null): Belief {
  const base = uniform();
  if (ageBand === null) return base;
  const lean = AGE_LEAN[ageBand];
  const leaning = normalise(
    Object.fromEntries(STYLES.map((style) => [style, lean[style] ?? 0])) as Belief,
  );
  const mixed = {} as Belief;
  for (const style of STYLES) {
    mixed[style] = (1 - AGE_PRIOR_WEIGHT) * base[style] + AGE_PRIOR_WEIGHT * leaning[style];
  }
  return mixed;
}

/** Appeal is kept away from 0 and 1 so no single swipe can rule a style out. */
const soften = (appeal: number) => 0.05 + 0.9 * Math.min(1, Math.max(0, appeal));

/** Bayes: a liked card raises the styles it appeals to; a disliked one lowers them. */
export function updateBelief(belief: Belief, card: SwipeCard, answer: Answer): Belief {
  if (answer === "unsure") return belief;
  const next = {} as Belief;
  for (const style of STYLES) {
    const appeal = soften(card.appeal[style]);
    next[style] = belief[style] * (answer === "love" ? appeal : 1 - appeal);
  }
  return normalise(next);
}

export function entropy(belief: Belief): number {
  return -STYLES.reduce((sum, style) => {
    const p = belief[style];
    return p > 0 ? sum + p * Math.log2(p) : sum;
  }, 0);
}

/** How much a card is expected to reduce our uncertainty, in bits. */
export function expectedGain(belief: Belief, card: SwipeCard): number {
  const pLove = STYLES.reduce((sum, style) => sum + belief[style] * soften(card.appeal[style]), 0);
  const afterLove = entropy(updateBelief(belief, card, "love"));
  const afterNo = entropy(updateBelief(belief, card, "no"));
  return entropy(belief) - (pLove * afterLove + (1 - pLove) * afterNo);
}

/** The unseen card that best separates the styles still in the running. */
export function nextCard(
  belief: Belief,
  deck: readonly SwipeCard[],
  seen: ReadonlySet<string>,
): SwipeCard | null {
  let best: SwipeCard | null = null;
  let bestGain = -Infinity;
  for (const card of deck) {
    if (seen.has(card.id)) continue;
    const gain = expectedGain(belief, card);
    // Ties break on deck order, so the choice is deterministic.
    if (gain > bestGain + 1e-12) {
      best = card;
      bestGain = gain;
    }
  }
  return best;
}

export interface Swipe {
  card_id: string;
  answer: Answer;
}

export function isDone(belief: Belief, swipes: readonly Swipe[], deckSize: number): boolean {
  if (swipes.length >= Math.min(MAX_SWIPES, deckSize)) return true;
  if (swipes.length < MIN_SWIPES) return false;
  const sorted = STYLES.map((style) => belief[style]).sort((a, b) => b - a);
  return (sorted[0] ?? 0) >= CONFIDENT || (sorted[0] ?? 0) + (sorted[1] ?? 0) >= TOP_TWO_CONFIDENT;
}

/** The planned number of cards shown in "4 of 10": 10, growing to 12 if needed. */
export function plannedTotal(swipes: number): number {
  return swipes < 10 ? 10 : MAX_SWIPES;
}

// --- What the swipes say ---------------------------------------------------------

const BLEND_MIN_WEIGHT = 0.1;

/** The taste as a blend of styles: those with a real share, renormalised. */
export function styleBlend(belief: Belief): { style: Style; weight: number }[] {
  const kept = STYLES.map((style) => ({ style, weight: belief[style] }))
    .filter((entry) => entry.weight >= BLEND_MIN_WEIGHT)
    .sort((a, b) => b.weight - a.weight);
  const top = kept.length > 0 ? kept : [{ style: STYLES[0] as Style, weight: 1 }];
  const total = top.reduce((sum, entry) => sum + entry.weight, 0);
  return top.map((entry) => ({
    style: entry.style,
    weight: Math.round((entry.weight / total) * 100) / 100,
  }));
}

function cardsById(deck: readonly SwipeCard[]) {
  return new Map(deck.map((card) => [card.id, card]));
}

/** Traits seen more in loved cards than in rejected ones, strongest first. */
export function tasteSoFar(
  swipes: readonly Swipe[],
  deck: readonly SwipeCard[],
  limit = 4,
): Trait[] {
  const cards = cardsById(deck);
  const score = new Map<Trait, number>();
  for (const swipe of swipes) {
    if (swipe.answer === "unsure") continue;
    for (const trait of cards.get(swipe.card_id)?.traits ?? []) {
      score.set(trait, (score.get(trait) ?? 0) + (swipe.answer === "love" ? 1 : -1));
    }
  }
  return [...score.entries()]
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([trait]) => trait);
}

const NEUTRAL: Attributes = {
  palette_warmth: 0.5,
  saturation: 0.5,
  boldness: 0.5,
  clutter_tolerance: 0.5,
  formality: 0.5,
  trend_vs_timeless: 0.5,
};

/**
 * Readable attributes: pulled toward loved cards and away from rejected
 * ones, starting from neutral. Always within 0 to 1.
 */
export function attributesFrom(swipes: readonly Swipe[], deck: readonly SwipeCard[]): Attributes {
  const cards = cardsById(deck);
  const out = { ...NEUTRAL };
  for (const key of Object.keys(NEUTRAL) as (keyof Attributes)[]) {
    let pull = 0;
    let count = 0;
    for (const swipe of swipes) {
      const card = cards.get(swipe.card_id);
      if (!card || swipe.answer === "unsure") continue;
      const offset = card.attributes[key] - 0.5;
      pull += swipe.answer === "love" ? offset : -offset;
      count += 1;
    }
    const value = count > 0 ? 0.5 + pull / count : 0.5;
    out[key] = Math.round(Math.min(1, Math.max(0, value)) * 100) / 100;
  }
  return out;
}
