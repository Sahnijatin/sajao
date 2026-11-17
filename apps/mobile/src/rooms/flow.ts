// The steps between "Looks good" on the review and the stages: the space
// profile for this room, then taste and budget the first time only. Pure.

export type FlowStep = "space" | "taste" | "generating";

export interface FlowFacts {
  /** A space profile exists for this room to confirm. */
  hasSpaceProfile: boolean;
  /** Taste and budget have been given before, on this phone. */
  hasTaste: boolean;
}

/** Where to go once the scan is confirmed. */
export function afterReview(facts: FlowFacts): FlowStep {
  if (facts.hasSpaceProfile) return "space";
  return afterSpace(facts);
}

/** Where to go once the space profile is confirmed. Taste is asked only once. */
export function afterSpace(facts: Pick<FlowFacts, "hasTaste">): FlowStep {
  return facts.hasTaste ? "generating" : "taste";
}
