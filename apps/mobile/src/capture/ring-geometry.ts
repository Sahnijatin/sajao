/**
 * Degrees of arc the progress ring draws for a share of 0 to 1. A full ring
 * stops just short of 360, because an arc of exactly 360 degrees draws nothing.
 */
export function ringSweepDegrees(progress: number): number {
  if (!Number.isFinite(progress) || progress <= 0) return 0;
  return Math.min(359.9, progress * 360);
}

/** Degrees left empty at the top and the bottom of a ring drawn in two halves. */
export const HALF_GAP_DEGREES = 6;

/**
 * The ring in two halves, each from 0 to 1: the first runs clockwise from
 * the top down the right side, the second from the bottom up the left. Start
 * angles are in degrees with 0 pointing right, as the drawing needs them.
 */
export function ringHalves(
  first: number,
  second: number,
): [{ start: number; sweep: number }, { start: number; sweep: number }] {
  const span = 180 - HALF_GAP_DEGREES;
  const share = (value: number) => (Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0);
  return [
    { start: -90 + HALF_GAP_DEGREES / 2, sweep: span * share(first) },
    { start: 90 + HALF_GAP_DEGREES / 2, sweep: span * share(second) },
  ];
}
