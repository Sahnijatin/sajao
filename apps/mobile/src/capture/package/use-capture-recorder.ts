// Records the capture package during an AR scan: native keyframe candidates
// judged by the recorder (dropped ones deleted at once), live detections,
// and a sensor log of AR poses. On Done the native view writes planes, the
// LiDAR mesh and depth, and the finished local capture waits for upload.
import type { CapturePackage } from "@sajao/schemas";
import { useCallback, useMemo, useRef } from "react";
import type { ArCaptureFiles, ArKeyframeEvent, SajaoArViewRef } from "../../../modules/sajao-ar";
import { useCaptureStore } from "@/state/capture";
import {
  addNativeKeyframe,
  chosenKeyframeUris,
  type LocalCapture,
  localCapture,
  sensorDue,
  sensorInterval,
} from "./native-capture";
import { record, type RecorderEvent, startRecording } from "./recorder";

type Detections = Extract<RecorderEvent, { type: "detections" }>["detections"];

const NO_FILES: ArCaptureFiles = { planes: null, sceneMesh: null, depth: null };

/** A capture id that is unique on this phone; it names the local folder. */
function newCaptureId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useCaptureRecorder(ar: CapturePackage["ar"]) {
  const captureId = useMemo(newCaptureId, []);
  const state = useRef(startRecording(Date.now(), ar));
  // Each sensor source is paced on its own, so one never crowds out another.
  const lastSensor = useRef<Record<string, number>>({});
  const viewRef = useRef<SajaoArViewRef>(null);
  const setLast = useCaptureStore((store) => store.setLast);

  const onKeyframe = useCallback((keyframe: ArKeyframeEvent) => {
    const step = addNativeKeyframe(state.current, keyframe, Date.now());
    state.current = step.state;
    if (step.discard.length > 0) void viewRef.current?.discardKeyframes(step.discard);
  }, []);

  const onDetections = useCallback((detections: Detections) => {
    state.current = record(state.current, { type: "detections", atMs: Date.now(), detections });
  }, []);

  const onSensor = useCallback((reading: Record<string, number | string | boolean>) => {
    const now = Date.now();
    const source = String(reading.source ?? "");
    if (!sensorDue(lastSensor.current[source] ?? null, now, sensorInterval(source))) return;
    lastSensor.current[source] = now;
    state.current = record(state.current, { type: "sensor", atMs: now, reading });
  }, []);

  /** End the capture: the native view writes its files; the local capture is kept for upload. */
  const finish = useCallback(async (): Promise<LocalCapture> => {
    let files = NO_FILES;
    try {
      files = (await viewRef.current?.finishCapture(chosenKeyframeUris(state.current))) ?? NO_FILES;
    } catch {
      // Keyframes, detections and the sensor log still make a package.
    }
    const local = localCapture(captureId, state.current, files, files.video ?? null);
    setLast(local);
    return local;
  }, [captureId, setLast]);

  return { captureId, viewRef, onKeyframe, onDetections, onSensor, finish };
}
