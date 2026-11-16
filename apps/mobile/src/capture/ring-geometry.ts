/**
 * Degrees of arc the progress ring draws for a share of 0 to 1. A full ring
 * stops just short of 360, because an arc of exactly 360 degrees draws nothing.
 */
export function ringSweepDegrees(progress: number): number {
  if (!Number.isFinite(progress) || progress <= 0) return 0;
  return Math.min(359.9, progress * 360);
}
