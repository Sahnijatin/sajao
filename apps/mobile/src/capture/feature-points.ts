// Feature points for the live scan mesh: corners found in the camera frame
// on the phone, with no AI and no server. A corner is a pixel where the
// image changes strongly in two directions (the Harris measure), which is
// where real edges of furniture, windows and tiles meet.
import type { GrayFrame } from "./frame-stats";

export interface FeaturePoint {
  /** Position as a fraction of the frame, 0 to 1, so it maps onto any screen size. */
  x: number;
  y: number;
  /** Corner strength; stronger points are drawn larger. */
  strength: number;
}

export interface FeatureOptions {
  /** At most this many points per frame. */
  maxPoints: number;
  /** The frame is divided into cells of this many pixels; one point per cell at most. */
  cellSize: number;
  /** Minimum corner strength, so flat walls and noise produce nothing. */
  minStrength: number;
}

export const DEFAULT_FEATURE_OPTIONS: FeatureOptions = {
  maxPoints: 60,
  cellSize: 12,
  minStrength: 4_000_000,
};

const HARRIS_K = 0.05;

export function detectFeaturePoints(
  frame: GrayFrame,
  options: FeatureOptions = DEFAULT_FEATURE_OPTIONS,
): FeaturePoint[] {
  "worklet";
  const { data, width, height } = frame;
  const { cellSize, maxPoints, minStrength } = options;
  if (width < 5 || height < 5) return [];

  // Image gradients (central differences).
  const gx = new Float32Array(width * height);
  const gy = new Float32Array(width * height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const i = y * width + x;
      gx[i] = ((data[i + 1] ?? 0) - (data[i - 1] ?? 0)) / 2;
      gy[i] = ((data[i + width] ?? 0) - (data[i - width] ?? 0)) / 2;
    }
  }

  // The strongest corner in each cell, so points spread over the frame.
  const best: FeaturePoint[] = [];
  for (let cellY = 2; cellY < height - 2; cellY += cellSize) {
    for (let cellX = 2; cellX < width - 2; cellX += cellSize) {
      let top = minStrength;
      let topX = -1;
      let topY = -1;
      const endY = Math.min(cellY + cellSize, height - 2);
      const endX = Math.min(cellX + cellSize, width - 2);
      for (let y = cellY; y < endY; y += 1) {
        for (let x = cellX; x < endX; x += 1) {
          // Structure tensor summed over a 3 by 3 window.
          let sxx = 0;
          let syy = 0;
          let sxy = 0;
          for (let dy = -1; dy <= 1; dy += 1) {
            for (let dx = -1; dx <= 1; dx += 1) {
              const j = (y + dy) * width + (x + dx);
              const ix = gx[j] ?? 0;
              const iy = gy[j] ?? 0;
              sxx += ix * ix;
              syy += iy * iy;
              sxy += ix * iy;
            }
          }
          const trace = sxx + syy;
          const response = sxx * syy - sxy * sxy - HARRIS_K * trace * trace;
          if (response > top) {
            top = response;
            topX = x;
            topY = y;
          }
        }
      }
      if (topX >= 0) best.push({ x: topX / width, y: topY / height, strength: top });
    }
  }

  best.sort((a, b) => b.strength - a.strength);
  return best.slice(0, maxPoints);
}
