// Scan guardrails: light, speed and shake, phone level, and mirrors and
// glare. Each shows as a live chip. When one fails for a while the scan
// pauses softly with a fix; it never throws an error and never loses what
// has been mapped.
import type { FrameStats } from "./frame-stats";

export type GuardrailId = "light" | "motion" | "level" | "glare";
export type GuardrailStatus = "good" | "warn";

export interface ScanReading extends FrameStats {
  /** How fast the phone is turning, in degrees per second. */
  rotationRate: number;
  /** Sideways tilt away from level, in degrees. */
  rollDegrees: number;
}

export interface Thresholds {
  /** Mean brightness below this is too dark for geometry. */
  minBrightness: number;
  /** Turning faster than this blurs frames. */
  maxRotationRate: number;
  /** Tilted further than this from level. */
  maxRollDegrees: number;
  /** More than this share of blown-out pixels. */
  maxGlare: number;
}

export const THRESHOLDS: Thresholds = {
  minBrightness: 45,
  maxRotationRate: 60,
  maxRollDegrees: 12,
  maxGlare: 0.12,
};

/**
 * A guardrail turns good again only after clearing its limit by this
 * margin, so a chip does not flicker when a reading hovers at the limit.
 */
const RECOVERY_MARGIN = 0.15;

export type GuardrailState = Record<GuardrailId, GuardrailStatus>;

export const ALL_GOOD: GuardrailState = {
  light: "good",
  motion: "good",
  level: "good",
  glare: "good",
};

function judge(
  previous: GuardrailStatus,
  value: number,
  limit: number,
  direction: "above" | "below",
): GuardrailStatus {
  "worklet";
  // "above": the value must stay at or above the limit (brightness).
  // "below": the value must stay at or below the limit (speed, tilt, glare).
  const margin = previous === "warn" ? RECOVERY_MARGIN : 0;
  if (direction === "above") return value >= limit * (1 + margin) ? "good" : "warn";
  return value <= limit * (1 - margin) ? "good" : "warn";
}

export function evaluateGuardrails(
  previous: GuardrailState,
  reading: ScanReading,
  thresholds: Thresholds = THRESHOLDS,
): GuardrailState {
  "worklet";
  return {
    light: judge(previous.light, reading.brightness, thresholds.minBrightness, "above"),
    motion: judge(previous.motion, reading.rotationRate, thresholds.maxRotationRate, "below"),
    level: judge(previous.level, Math.abs(reading.rollDegrees), thresholds.maxRollDegrees, "below"),
    glare: judge(previous.glare, reading.glare, thresholds.maxGlare, "below"),
  };
}

/** Which failing guardrail to explain first: the one whose fix helps most. */
const PRIORITY: readonly GuardrailId[] = ["light", "motion", "glare", "level"];

export interface PauseState {
  paused: boolean;
  /** The guardrail the pause sheet explains, when paused. */
  reason: GuardrailId | null;
  /** How long any guardrail has been failing without a break, in ms. */
  failingForMs: number;
  /** The user chose "Scan anyway": do not pause again for this reason. */
  overridden: readonly GuardrailId[];
}

export const NOT_PAUSED: PauseState = {
  paused: false,
  reason: null,
  failingForMs: 0,
  overridden: [],
};

/** A brief wobble is not worth interrupting; a sustained problem is. */
export const PAUSE_AFTER_MS = 1500;

export function updatePause(
  previous: PauseState,
  guardrails: GuardrailState,
  elapsedMs: number,
): PauseState {
  "worklet";
  const failing = PRIORITY.filter(
    (id) => guardrails[id] === "warn" && !previous.overridden.includes(id),
  );
  // Level is a nudge only: a tilted phone still captures usable frames.
  const blocking = failing.filter((id) => id !== "level");

  if (previous.paused) {
    // Stay paused until the reason is fixed; then resume on its own.
    const stillFailing = blocking.some((id) => id === previous.reason);
    return stillFailing ? previous : { ...previous, paused: false, reason: null, failingForMs: 0 };
  }
  if (blocking.length === 0) return { ...previous, failingForMs: 0 };

  const failingForMs = previous.failingForMs + elapsedMs;
  if (failingForMs < PAUSE_AFTER_MS) return { ...previous, failingForMs };
  return { ...previous, paused: true, reason: blocking[0] ?? null, failingForMs };
}

/** "Scan anyway": resume and stop pausing for that reason. */
export function scanAnyway(state: PauseState): PauseState {
  if (!state.paused || state.reason === null) return state;
  return {
    paused: false,
    reason: null,
    failingForMs: 0,
    overridden: [...state.overridden, state.reason],
  };
}

/** Frames are only used for the mesh and kept for upload while the scan is not paused. */
export function shouldUseFrame(pause: PauseState, guardrails: GuardrailState): boolean {
  return !pause.paused && guardrails.motion === "good";
}
