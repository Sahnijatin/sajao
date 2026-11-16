// Turns the native AR view's events into scan session events. Pure, so the
// thresholds are tested without a phone.
import type { ArTracking, ScanEvent } from "../scan-session";

export interface ArStatus {
  tracking: string;
  brightness: number;
  ambientIntensity: number;
  featurePoints: number;
  /** Missing from older builds. */
  planes?: number;
  meshTriangles?: number;
  detector?: boolean;
  detectorError?: string;
}

/**
 * ARKit's light estimate in lumens: about 1000 in a well-lit room. Below
 * this the room is dim even when auto exposure keeps the picture bright,
 * like the camera ISO check in the 2D scan. Android reports no such value.
 */
export const IOS_LOW_LIGHT_LUMENS = 150;

export function trackingOf(name: string): ArTracking {
  switch (name) {
    case "normal":
    case "initializing":
    case "limited":
    case "notAvailable":
      return name;
    default:
      return "none";
  }
}

export function arFrameEvent(
  status: ArStatus,
  platform: "ios" | "android",
  atMs: number,
): Extract<ScanEvent, { type: "arFrame" }> {
  return {
    type: "arFrame",
    brightness: Number.isFinite(status.brightness) ? status.brightness : 128,
    lowLight: platform === "ios" && status.ambientIntensity < IOS_LOW_LIGHT_LUMENS,
    featureCount: Math.max(0, Math.round(status.featurePoints)),
    tracking: trackingOf(status.tracking),
    signals: {
      planes: count(status.planes),
      meshTriangles: count(status.meshTriangles),
      detector: status.detector === true,
      detectorFailed: typeof status.detectorError === "string" && status.detectorError !== "",
    },
    atMs,
  };
}

const count = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;

export function arPoseEvent(
  pose: { yaw: number; pitch: number; tracking: string; x?: number; z?: number },
  atMs: number,
): Extract<ScanEvent, { type: "arPose" }> {
  const position =
    Number.isFinite(pose.x) && Number.isFinite(pose.z)
      ? { x: pose.x as number, z: pose.z as number }
      : null;
  return {
    type: "arPose",
    yaw: pose.yaw,
    pitch: pose.pitch,
    tracking: trackingOf(pose.tracking),
    position,
    atMs,
  };
}
