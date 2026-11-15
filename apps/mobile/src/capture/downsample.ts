// Shrink a camera frame's brightness plane to a small grayscale image. All
// on-device analysis runs on this copy, so its cost does not grow with the
// camera resolution.
import type { GrayFrame } from "./frame-stats";

export const ANALYSIS_WIDTH = 96;

export function downsampleLuma(
  /** The brightness (Y) plane: one byte per pixel, rows padded to bytesPerRow. */
  plane: ArrayBuffer,
  size: { width: number; height: number; bytesPerRow: number },
  targetWidth: number = ANALYSIS_WIDTH,
): GrayFrame {
  "worklet";
  const source = new Uint8Array(plane);
  const width = Math.min(targetWidth, size.width);
  const height = Math.max(1, Math.round((size.height * width) / Math.max(1, size.width)));
  const data = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    const sourceY = Math.min(size.height - 1, Math.floor((y * size.height) / height));
    for (let x = 0; x < width; x += 1) {
      const sourceX = Math.min(size.width - 1, Math.floor((x * size.width) / width));
      data[y * width + x] = source[sourceY * size.bytesPerRow + sourceX] ?? 0;
    }
  }
  return { data, width, height };
}
