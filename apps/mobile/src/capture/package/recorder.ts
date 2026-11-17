// Records what the twin needs during a scan: keyframes, AR poses, live
// detections and a sensor log. Pure: events in, state out. The manifest it
// builds becomes Capture.package once the files are uploaded.
import type { CapturePackage, LiveDetection } from "@sajao/schemas";
import {
  chosenKeyframes,
  type KeyframeCandidate,
  type KeyframeSet,
  NO_KEYFRAMES,
  offerKeyframe,
} from "./keyframes";

export interface ArPoseSample {
  position: { x_m: number; y_m: number; z_m: number };
  /** Unit quaternion x, y, z, w. */
  rotation: [number, number, number, number];
}

export interface Intrinsics {
  fx: number;
  fy: number;
  cx: number;
  cy: number;
  width_px: number;
  height_px: number;
}

export interface RecordedKeyframe extends KeyframeCandidate {
  pose: ArPoseSample | null;
  intrinsics: Intrinsics | null;
}

export interface RecorderState {
  startedAtMs: number;
  ar: CapturePackage["ar"];
  keyframes: KeyframeSet;
  /** Pose and intrinsics per keyframe uri, when AR ran. */
  poses: ReadonlyMap<string, { pose: ArPoseSample; intrinsics: Intrinsics }>;
  detections: readonly LiveDetection[];
  /** JSON lines: one reading per line. */
  sensorLog: readonly string[];
}

export const MAX_DETECTIONS = 4000;
export const MAX_SENSOR_LINES = 20000;

export function startRecording(startedAtMs: number, ar: CapturePackage["ar"]): RecorderState {
  return {
    startedAtMs,
    ar,
    keyframes: NO_KEYFRAMES,
    poses: new Map(),
    detections: [],
    sensorLog: [],
  };
}

export type RecorderEvent =
  | { type: "keyframe"; frame: RecordedKeyframe }
  | {
      type: "detections";
      atMs: number;
      detections: {
        detectorClass: string;
        score: number;
        world: { x: number; y: number; z: number } | null;
      }[];
    }
  | { type: "sensor"; atMs: number; reading: Record<string, number | string | boolean> };

const elapsed = (state: RecorderState, atMs: number) =>
  Math.max(0, Math.round(atMs - state.startedAtMs));

export function record(state: RecorderState, event: RecorderEvent): RecorderState {
  switch (event.type) {
    case "keyframe": {
      const frame = { ...event.frame, atMs: elapsed(state, event.frame.atMs) };
      const keyframes = offerKeyframe(state.keyframes, frame);
      if (keyframes === state.keyframes) return state;
      const poses = new Map(state.poses);
      if (frame.pose && frame.intrinsics) {
        poses.set(frame.uri, { pose: frame.pose, intrinsics: frame.intrinsics });
      }
      return { ...state, keyframes, poses };
    }
    case "detections": {
      const room = MAX_DETECTIONS - state.detections.length;
      if (room <= 0) return state;
      const at_ms = elapsed(state, event.atMs);
      const added: LiveDetection[] = event.detections.slice(0, room).map((detection) => ({
        detector_class: detection.detectorClass,
        score: Math.min(1, Math.max(0, detection.score)),
        at_ms,
        ...(detection.world
          ? { world: { x_m: detection.world.x, y_m: detection.world.y, z_m: detection.world.z } }
          : {}),
      }));
      return { ...state, detections: [...state.detections, ...added] };
    }
    case "sensor": {
      if (state.sensorLog.length >= MAX_SENSOR_LINES) return state;
      const line = JSON.stringify({ t: elapsed(state, event.atMs), ...event.reading });
      return { ...state, sensorLog: [...state.sensorLog, line] };
    }
  }
}

/** The local files to upload, named as they will be stored. */
export interface PackageFiles {
  keyframes: { id: string; uri: string }[];
  video: string | null;
  planes: string | null;
  sceneMesh: string | null;
  depth: string | null;
}

export function filesToUpload(
  state: RecorderState,
  extras: Omit<PackageFiles, "keyframes">,
): PackageFiles {
  return {
    ...extras,
    keyframes: chosenKeyframes(state.keyframes).map((frame, index) => ({
      id: `k${index + 1}`,
      uri: frame.uri,
    })),
  };
}

/**
 * Build Capture.package from uploaded storage keys. Every keyframe must have
 * been uploaded; a missing key is a bug, so it throws rather than guessing.
 */
export function buildPackage(
  state: RecorderState,
  keys: {
    keyframes: Record<string, string>;
    sensorLog: string;
    video?: string;
    planes?: string;
    sceneMesh?: string;
    depth?: string;
  },
): CapturePackage {
  const keyframes = chosenKeyframes(state.keyframes).map((frame, index) => {
    const id = `k${index + 1}`;
    const image = keys.keyframes[id];
    if (!image) throw new Error(`Keyframe ${id} was not uploaded`);
    const posed = state.poses.get(frame.uri);
    return {
      id,
      image,
      captured_at_ms: frame.atMs,
      sharpness: frame.sharpness,
      ...(posed ? { pose: posed.pose, intrinsics: posed.intrinsics } : {}),
    };
  });
  const [first, ...rest] = keyframes;
  if (!first) throw new Error("A capture package needs at least one keyframe");
  return {
    ar: state.ar,
    keyframes: [first, ...rest],
    detections: [...state.detections],
    sensor_log: keys.sensorLog,
    ...(keys.video ? { video: keys.video } : {}),
    ...(keys.planes ? { planes: keys.planes } : {}),
    ...(keys.sceneMesh ? { scene_mesh: keys.sceneMesh } : {}),
    ...(keys.depth ? { depth: keys.depth } : {}),
  };
}
