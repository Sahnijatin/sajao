// Everything the scan does with one camera frame, as a single worklet. It
// runs on the camera thread, where module scope does not exist: every name
// it uses must be a captured constant or another worklet. The isolation
// test runs it with no module scope to keep it that way.
import { downsampleLuma } from "./downsample";
import { detectFeaturePoints, type FeaturePoint } from "./feature-points";
import { type FrameStats, frameStats } from "./frame-stats";
import { type FrameOrientation, uprightAspect, uprightPoint } from "./orientation";

/** The parts of a camera frame the analysis reads. */
export interface FrameLike {
  readonly orientation: string;
  readonly isMirrored: boolean;
  getPlanes(): readonly {
    readonly width: number;
    readonly height: number;
    readonly bytesPerRow: number;
    getPixelBuffer(): ArrayBuffer;
  }[];
}

export interface FrameAnalysis {
  stats: FrameStats;
  /** Feature points in the upright frame, 0 to 1 on both axes. */
  points: FeaturePoint[];
  /** Width over height of the upright frame. */
  aspect: number;
}

/** Analyse one frame's brightness plane; null when the frame has none. */
export function analyseFrame(frame: FrameLike): FrameAnalysis | null {
  "worklet";
  const luma = frame.getPlanes()[0];
  if (!luma) return null;
  const gray = downsampleLuma(luma.getPixelBuffer(), {
    width: luma.width,
    height: luma.height,
    bytesPerRow: luma.bytesPerRow,
  });
  const orientation = frame.orientation as FrameOrientation;
  const mirrored = frame.isMirrored;
  const found = detectFeaturePoints(gray);
  const points: FeaturePoint[] = [];
  // Plain index loops: iterator helpers that a compiler might add would
  // live in module scope, which the camera thread does not have.
  for (let i = 0; i < found.length; i += 1) {
    const point = found[i];
    if (!point) continue;
    const upright = uprightPoint(point.x, point.y, orientation, mirrored);
    points.push({ x: upright.x, y: upright.y, strength: point.strength });
  }
  return {
    stats: frameStats(gray),
    points,
    aspect: uprightAspect(luma.width, luma.height, orientation),
  };
}
