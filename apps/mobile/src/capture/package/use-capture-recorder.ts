// Records the capture package during an AR scan: native keyframe candidates
// judged by the recorder (dropped ones deleted at once), live detections,
// and a sensor log of AR poses. On Done the native view writes planes, the
// LiDAR mesh and depth, and the finished local capture waits for upload.
import type { CapturePackage } from "@sajao/schemas";
import { useCallback, useMemo, useRef, useState } from "react";
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
import { uuidV4 } from "./upload-capture";

type Detections = Extract<RecorderEvent, { type: "detections" }>["detections"];

const NO_FILES: ArCaptureFiles = { planes: null, sceneMesh: null, depth: null };

export function useCaptureRecorder(ar: CapturePackage["ar"]) {
  // A UUID: it names the local folder and is the capture's id on the server.
  const captureId = useMemo(() => uuidV4(), []);
  const state = useRef(startRecording(Date.now(), ar));
  // Each sensor source is paced on its own, so one never crowds out another.
  const lastSensor = useRef<Record<string, number>>({});
  const viewRef = useRef<SajaoArViewRef>(null);
  const [capturePaused, setCapturePaused] = useState(false);
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
    // The native view starts the video with the AR session's first frame;
    // its first pose is the nearest the app can see to that moment.
    if (reading.source === "ar_pose" && state.current.videoStartMs === null) {
      state.current = record(state.current, { type: "videoStart", atMs: now });
    }
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
    // A review still open at Done runs to the end of the capture.
    state.current = record(state.current, { type: "review", open: false, atMs: Date.now() });
    const local = localCapture(captureId, state.current, files, files.video ?? null);
    setLast(local);
    return local;
  }, [captureId, setLast]);

  /**
   * The review opened over the scan (true) or the person chose to rescan
   * (false). While open nothing is recorded: pass `capturePaused` to the AR
   * view, which then saves no keyframe and, on iOS, no video frame. The
   * window also goes into the package, for the video ARCore cannot pause.
   */
  const setReviewOpen = useCallback((open: boolean) => {
    state.current = record(state.current, { type: "review", open, atMs: Date.now() });
    setCapturePaused(open);
  }, []);

  return {
    captureId,
    viewRef,
    onKeyframe,
    onDetections,
    onSensor,
    finish,
    setReviewOpen,
    capturePaused,
  };
}
