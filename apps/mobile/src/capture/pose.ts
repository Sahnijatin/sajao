// Phone pose from the motion sensors, in a form both platforms agree on.
//
// expo-sensors labels turn rates differently per platform: the turn about
// the phone's long (vertical) axis is `beta` on both, but the turn about the
// short (sideways) axis is `gamma` on iOS and `alpha` on Android. Tilt is
// read from gravity as magnitudes only, because the sign of gravity also
// differs between platforms.

export interface RawMotion {
  /** Turn rates in degrees per second, labelled as expo-sensors reports them. */
  rotationRate?: { alpha: number; beta: number; gamma: number } | null;
  /** Acceleration without gravity, in m/s². */
  acceleration?: { x: number; y: number; z: number } | null;
  /** Acceleration with gravity, in m/s². */
  accelerationIncludingGravity?: { x: number; y: number; z: number } | null;
}

export interface MotionSample {
  /** Total turn rate, degrees per second. */
  rotationRate: number;
  /** Turn rate about the phone's vertical axis (panning left and right), degrees per second. Positive turns left. */
  yawRate: number;
  /** Turn rate about the phone's sideways axis (tilting up and down), degrees per second. Positive tilts the camera up. */
  pitchRate: number;
  /** Shake: acceleration without gravity, m/s². */
  acceleration: number;
  /** Sideways tilt away from upright, degrees, 0 or more. */
  rollDegrees: number;
  /** Camera tilt up or down away from the horizon, degrees, 0 or more. */
  pitchDegrees: number;
  /** False when the phone has no gyroscope: coverage then falls back to frames. */
  hasGyro: boolean;
}

const DEG = 180 / Math.PI;

export function motionSample(reading: RawMotion, platform: "ios" | "android"): MotionSample {
  const rate = reading.rotationRate;
  const hasGyro = !!rate && [rate.alpha, rate.beta, rate.gamma].every(Number.isFinite);
  const yawRate = hasGyro ? rate.beta : 0;
  const pitchRate = hasGyro ? (platform === "ios" ? rate.gamma : rate.alpha) : 0;
  const rotationRate = hasGyro ? Math.hypot(rate.alpha, rate.beta, rate.gamma) : 0;

  const a = reading.acceleration;
  const acceleration = a ? Math.hypot(a.x, a.y, a.z) : 0;

  const g = reading.accelerationIncludingGravity;
  const gravity = g ? Math.hypot(g.x, g.y, g.z) : 0;
  const rollDegrees = g && gravity > 1 ? Math.atan2(Math.abs(g.x), Math.abs(g.y)) * DEG : 0;
  const pitchDegrees = g && gravity > 1 ? Math.asin(Math.min(1, Math.abs(g.z) / gravity)) * DEG : 0;

  return {
    rotationRate: Number.isFinite(rotationRate) ? rotationRate : 0,
    yawRate,
    pitchRate,
    acceleration: Number.isFinite(acceleration) ? acceleration : 0,
    rollDegrees,
    pitchDegrees,
    hasGyro,
  };
}

/** Wrap an angle to the range -180 to 180 degrees. */
export function wrapDegrees(angle: number): number {
  const wrapped = ((((angle + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 ? 180 : wrapped;
}
