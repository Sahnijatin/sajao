// Cheap measurements on a small grayscale copy of a camera frame. No AI:
// plain arithmetic that runs on the phone for every analysed frame.

export interface GrayFrame {
  /** One byte of brightness per pixel, row by row. */
  data: Uint8Array;
  width: number;
  height: number;
}

export interface FrameStats {
  /** Mean brightness, 0 (black) to 255 (white). */
  brightness: number;
  /** Share of pixels that are blown out, 0 to 1: mirrors, glare, bare bulbs. */
  glare: number;
  /** Variance of the Laplacian: higher is sharper; a blurred frame scores low. */
  sharpness: number;
}

const BLOWN_OUT = 250;

export function frameStats(frame: GrayFrame): FrameStats {
  "worklet";
  const { data, width, height } = frame;
  const total = width * height;
  if (total === 0) return { brightness: 0, glare: 0, sharpness: 0 };

  let sum = 0;
  let blown = 0;
  for (let i = 0; i < total; i += 1) {
    const value = data[i] ?? 0;
    sum += value;
    if (value >= BLOWN_OUT) blown += 1;
  }

  let laplacianSum = 0;
  let laplacianSquares = 0;
  let count = 0;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const i = y * width + x;
      const laplacian =
        (data[i - 1] ?? 0) +
        (data[i + 1] ?? 0) +
        (data[i - width] ?? 0) +
        (data[i + width] ?? 0) -
        4 * (data[i] ?? 0);
      laplacianSum += laplacian;
      laplacianSquares += laplacian * laplacian;
      count += 1;
    }
  }
  const mean = count ? laplacianSum / count : 0;
  const sharpness = count ? laplacianSquares / count - mean * mean : 0;

  return { brightness: sum / total, glare: blown / total, sharpness };
}
