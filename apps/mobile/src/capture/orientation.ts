// Camera frames arrive in the sensor's own orientation (usually landscape),
// not the way the phone is held. Feature points are found in that raw frame
// and turned upright here, so the mesh lands where the preview shows it.
// The rotation matches the camera library's own frame-to-view conversion.

export type FrameOrientation = "up" | "right" | "down" | "left";

/** A point in the raw frame (0 to 1 on both axes), turned upright. */
export function uprightPoint(
  x: number,
  y: number,
  orientation: FrameOrientation,
  isMirrored: boolean,
): { x: number; y: number } {
  "worklet";
  const sx = isMirrored ? 1 - x : x;
  switch (orientation) {
    case "right":
      return { x: y, y: 1 - sx };
    case "left":
      return { x: 1 - y, y: sx };
    case "down":
      return { x: 1 - sx, y: 1 - y };
    default:
      return { x: sx, y };
  }
}

/** Width over height of the frame once it is upright. */
export function uprightAspect(width: number, height: number, orientation: FrameOrientation) {
  "worklet";
  if (width <= 0 || height <= 0) return 1;
  return orientation === "left" || orientation === "right" ? height / width : width / height;
}

/**
 * The preview fills the screen and crops the overflow ("cover"). Maps an
 * upright frame point (0 to 1) to screen pixels with the same crop.
 */
export function coverToScreen(
  point: { x: number; y: number },
  frameAspect: number,
  screen: { width: number; height: number },
): { x: number; y: number } {
  const screenAspect = screen.width / Math.max(1, screen.height);
  if (frameAspect > screenAspect) {
    // Frame is wider than the screen: full height shown, sides cropped.
    const shownWidth = screen.height * frameAspect;
    return {
      x: point.x * shownWidth - (shownWidth - screen.width) / 2,
      y: point.y * screen.height,
    };
  }
  const shownHeight = screen.width / frameAspect;
  return {
    x: point.x * screen.width,
    y: point.y * shownHeight - (shownHeight - screen.height) / 2,
  };
}
