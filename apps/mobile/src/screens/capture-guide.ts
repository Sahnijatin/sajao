// What the scan screen says and when it ticks. One plain instruction at a
// time, chosen from what the scan session already reports; nothing here
// changes how coverage is counted.
import type { Hint } from "@/capture/ar/guidance";
import type { GuardrailId } from "@/capture/guardrails";
import type { LabelKind } from "@/capture/ar/labels";

export type InstructionId =
  | "move"
  | "corners"
  | "slowDown"
  | "stepBack"
  | "walkAround"
  | "walk"
  | "doorway"
  | "almost"
  | "complete"
  | "walkWalls"
  | "keepGoing"
  | "standMiddle"
  | "tiltDown"
  | "oneMoreSpot"
  | "dark"
  | "fast"
  | "glare";

export interface Instruction {
  id: InstructionId;
  /** The object to walk around, for "walkAround". */
  kind?: LabelKind;
  /**
   * guide: the steady instruction. nudge: shown only while something needs
   * fixing. fix: the scan is paused until it is fixed or you choose to go on.
   */
  tone: "guide" | "nudge" | "fix";
}

/** Past this share the walls are mostly in and the gaps are in the corners. */
export const CORNERS_FROM_SHARE = 0.5;

const FIXES: Record<Exclude<GuardrailId, "level">, InstructionId> = {
  light: "dark",
  motion: "fast",
  glare: "glare",
};

const HINTS: Record<NonNullable<Hint>["id"], { id: InstructionId; tone: Instruction["tone"] }> = {
  doorway: { id: "doorway", tone: "nudge" },
  slowDown: { id: "slowDown", tone: "nudge" },
  stepBack: { id: "stepBack", tone: "nudge" },
  walkAround: { id: "walkAround", tone: "nudge" },
  walk: { id: "walk", tone: "nudge" },
  coverMore: { id: "almost", tone: "guide" },
  complete: { id: "complete", tone: "guide" },
  // The coverage meter's next step: these are the scan's steady instructions.
  walkWalls: { id: "walkWalls", tone: "guide" },
  keepGoing: { id: "keepGoing", tone: "guide" },
  standMiddle: { id: "standMiddle", tone: "guide" },
  tiltDown: { id: "tiltDown", tone: "nudge" },
  oneMoreSpot: { id: "oneMoreSpot", tone: "guide" },
  meterDone: { id: "complete", tone: "guide" },
};

/**
 * The one instruction to show: a pause to fix first, then the session's own
 * hint, then the steady guide for how far the scan has come.
 */
export function scanInstruction(input: {
  /** Why the scan is paused, if it is. A tilted phone never pauses the scan. */
  pausedFor: GuardrailId | null;
  hint: Hint;
  /** 0 to 1. */
  share: number;
  /** Done is on. */
  ready: boolean;
}): Instruction {
  if (input.pausedFor && input.pausedFor !== "level") {
    return { id: FIXES[input.pausedFor], tone: "fix" };
  }
  if (input.hint) {
    const mapped = HINTS[input.hint.id];
    return input.hint.id === "walkAround" ? { ...mapped, kind: input.hint.kind } : mapped;
  }
  if (input.ready) return { id: "almost", tone: "guide" };
  return { id: input.share >= CORNERS_FROM_SHARE ? "corners" : "move", tone: "guide" };
}

/** A tick each time coverage passes another tenth. */
export const TICK_STEPS = 10;

/** Which tenth the scan has reached, 0 to 10. */
export function coverageStep(share: number): number {
  if (!Number.isFinite(share)) return 0;
  return Math.floor(Math.min(1, Math.max(0, share)) * TICK_STEPS + 1e-9);
}

/** True when coverage has grown into a new tenth since the last tick. */
export function shouldTick(previousStep: number, share: number): boolean {
  return coverageStep(share) > previousStep;
}
