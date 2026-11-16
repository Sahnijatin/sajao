// Glue between the native AR view's capture files and the recorder. The
// native view saves keyframe candidates; the recorder (keyframes.ts) is the
// judge, so every candidate it does not keep is deleted at once to bound
// disk use. Pure: returns what to delete instead of deleting.
import type { CapturePackage } from "@sajao/schemas";
import { chosenKeyframes, replacedBy } from "./keyframes";
import { filesToUpload, type PackageFiles, record, type RecorderState } from "./recorder";

export interface NativeKeyframe {
  uri: string;
  sharpness: number;
  /** Where the camera pointed; missing while tracking was lost (the frame is still kept). */
  yaw?: number;
  pitch?: number;
  depth: boolean;
  /** AR tracking was normal when the frame was taken. */
  tracking?: boolean;
  /** Missing while tracking was lost: the server solves the pose from the video. */
  pose?: {
    position: { x_m: number; y_m: number; z_m: number };
    rotation: [number, number, number, number];
  };
  intrinsics: {
    fx: number;
    fy: number;
    cx: number;
    cy: number;
    width_px: number;
    height_px: number;
  };
}

/** Record a native keyframe candidate; returns the new state and the files to delete. */
export function addNativeKeyframe(
  state: RecorderState,
  keyframe: NativeKeyframe,
  atMs: number,
): { state: RecorderState; discard: string[] } {
  const next = record(state, {
    type: "keyframe",
    frame: {
      uri: keyframe.uri,
      atMs,
      sharpness: keyframe.sharpness,
      yaw: keyframe.pose ? (keyframe.yaw ?? null) : null,
      pitch: keyframe.pose ? (keyframe.pitch ?? null) : null,
      pose: keyframe.pose ?? null,
      intrinsics: keyframe.intrinsics,
    },
  });
  if (next === state) return { state, discard: [keyframe.uri] };
  return { state: next, discard: replacedBy(state.keyframes, next.keyframes) };
}

/** The chosen keyframes' files in package order: k1, k2, ... */
export function chosenKeyframeUris(state: RecorderState): string[] {
  return chosenKeyframes(state.keyframes).map((frame) => frame.uri);
}

/** A finished scan on the phone: what to upload, and the state to build the package from. */
export interface LocalCapture {
  captureId: string;
  state: RecorderState;
  files: PackageFiles;
}

/** Put the recorder state and the native files together once the native view has finished. */
export function localCapture(
  captureId: string,
  state: RecorderState,
  native: { planes: string | null; sceneMesh: string | null; depth: string | null },
  video: string | null = null,
): LocalCapture {
  const ar: CapturePackage["ar"] = { ...state.ar, depth: native.depth !== null };
  const final = { ...state, ar };
  return {
    captureId,
    state: final,
    files: filesToUpload(final, {
      video,
      planes: native.planes,
      sceneMesh: native.sceneMesh,
      depth: native.depth,
    }),
  };
}

/** Sensor readings are logged at most this often. */
export const SENSOR_INTERVAL_MS = 200;

/** True when a sensor reading at `atMs` should be logged after one at `lastMs`. */
export function sensorDue(lastMs: number | null, atMs: number): boolean {
  return lastMs === null || atMs - lastMs >= SENSOR_INTERVAL_MS;
}
