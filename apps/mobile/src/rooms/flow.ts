// The steps between adding a room and its stages: taste, with the first
// room's budget, the first time; this room's budget after that. The upload
// and the room's analysis run meanwhile. Pure.

export type FlowStep = "taste" | "budget";

export interface FlowFacts {
  /** Taste and budget have been given before, on this phone. */
  hasTaste: boolean;
}

/** Where to go once a room is added: the questions, while its photos upload. */
export function afterAdding(facts: FlowFacts): FlowStep {
  return facts.hasTaste ? "budget" : "taste";
}

/** The route for a flow step, for one room. */
export function flowRoute(step: FlowStep, room: string) {
  return { pathname: step === "taste" ? "/taste" : "/budget", params: { room } } as const;
}

/**
 * Where to go once the room is measured. A scan of several areas stops to
 * ask which one to redesign, once; everything else goes straight on.
 */
export function afterMeasured(facts: { areas: number; chosen: boolean }): "areas" | "on" {
  return facts.areas > 1 && !facts.chosen ? "areas" : "on";
}
