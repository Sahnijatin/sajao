// Motion presets, from docs/10-design-language-and-motion.md. Motion has a
// job: it shows where something came from or confirms an action.
import type { DeviceTier } from "./deviceTier";

export type Bezier = readonly [number, number, number, number];

export const motion = {
  /** Screen and sheet transitions: cubic-bezier(.32, .72, 0, 1) over 0.45 s. */
  ease: { bezier: [0.32, 0.72, 0, 1], durationMs: 450 },
  /** Press feedback on button-like controls. */
  press: { scale: 0.97, bezier: [0.23, 1, 0.32, 1], durationMs: 120 },
  /** Chips, toggles, item selection. */
  selectionSpring: { stiffness: 380, damping: 32, mass: 1 },
  /** Lists and panels resizing: critically damped over 0.45 s. */
  layoutGlide: { duration: 450, dampingRatio: 1 },
} as const satisfies Record<string, object>;

export interface MotionContext {
  reducedMotion: boolean;
  tier: DeviceTier;
}

/** Low-tier phones get shorter animations. */
const LOW_TIER_DURATION_SCALE = 2 / 3;

/**
 * The duration to actually run. Reduced motion turns every animation into
 * an instant change; the low tier shortens it.
 */
export function resolveDuration(durationMs: number, { reducedMotion, tier }: MotionContext) {
  if (reducedMotion) return 0;
  return tier === "low" ? Math.round(durationMs * LOW_TIER_DURATION_SCALE) : durationMs;
}
