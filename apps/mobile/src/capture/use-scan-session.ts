import { useTheme } from "@sajao/ui";
import { DeviceMotion } from "expo-sensors";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { Platform } from "react-native";
import { arFrameEvent, type ArStatus, arPoseEvent } from "./ar/ar-events";
import { type Detection, EMPTY_LABELS, type LabelState, updateLabels } from "./ar/labels";
import { motionSample } from "./pose";
import type { AnalysedFrame, CameraDiagnostics } from "./scan-camera";
import { INITIAL_SCAN, scanReducer } from "./scan-session";

const MOTION_INTERVAL_MS = 100;
const DEBUG_WINDOW_MS = 1000;

/** Numbers for the hidden debug overlay, refreshed about once a second. */
export interface ScanDebug {
  /** Frames the frame callback received per second. */
  cameraFps: number;
  /** Frames analysed per second. */
  analysedFps: number;
  /** Feature points in the latest analysed frame. */
  featurePoints: number;
  analysisMs: number;
  /** Seconds since the screen opened with no frame received; 0 once frames arrive. */
  waitingSeconds: number;
  diagnostics: CameraDiagnostics;
  /** AR scan numbers, when the AR view is running. */
  ar: ArDebug | null;
}

export interface ArDebug {
  tracking: string;
  lidar: boolean;
  planes: number;
  meshTriangles: number;
  mappedPoints: number;
  detector: boolean;
  labels: number;
}

const EMPTY_DEBUG: ScanDebug = {
  cameraFps: 0,
  analysedFps: 0,
  featurePoints: 0,
  analysisMs: 0,
  waitingSeconds: 0,
  diagnostics: { dropped: 0, lastError: null },
  ar: null,
};

/** Scan state driven by analysed camera frames and the phone's motion sensors. */
export function useScanSession(active: boolean) {
  const { tier } = useTheme();
  const reducer = useMemo(() => scanReducer(tier), [tier]);
  const [state, dispatch] = useReducer(reducer, INITIAL_SCAN);
  const [debug, setDebug] = useState<ScanDebug>(EMPTY_DEBUG);
  const counters = useRef({
    startMs: Date.now(),
    analysed: 0,
    firstSeen: -1,
    lastSeen: 0,
    last: null as AnalysedFrame | null,
    diagnostics: EMPTY_DEBUG.diagnostics,
    ar: null as ArDebug | null,
  });
  const [labels, setLabels] = useState<LabelState>(EMPTY_LABELS);

  useEffect(() => {
    if (!active) return;
    const platform = Platform.OS === "ios" ? "ios" : "android";
    DeviceMotion.setUpdateInterval(MOTION_INTERVAL_MS);
    const subscription = DeviceMotion.addListener((reading) => {
      dispatch({ type: "motion", sample: motionSample(reading, platform), atMs: Date.now() });
    });
    return () => subscription.remove();
  }, [active]);

  // Debug numbers are counted on every frame but published once a second,
  // so the overlay never adds work to each frame.
  useEffect(() => {
    if (!active) return;
    const opened = Date.now();
    const timer = setInterval(() => {
      const w = counters.current;
      const now = Date.now();
      const seconds = Math.max(0.001, (now - w.startMs) / 1000);
      const seen = w.firstSeen < 0 ? 0 : w.lastSeen - w.firstSeen;
      setDebug({
        cameraFps: Math.round(seen / seconds),
        analysedFps: Math.round(w.analysed / seconds),
        featurePoints: w.last?.points.length ?? 0,
        analysisMs: w.last?.analysisMs ?? 0,
        waitingSeconds: w.last ? 0 : Math.round((now - opened) / 1000),
        diagnostics: w.diagnostics,
        ar: w.ar,
      });
      w.startMs = now;
      w.analysed = 0;
      w.firstSeen = w.lastSeen;
    }, DEBUG_WINDOW_MS);
    return () => clearInterval(timer);
  }, [active]);

  const onFrame = useCallback((frame: AnalysedFrame) => {
    const w = counters.current;
    w.analysed += 1;
    if (w.firstSeen < 0) w.firstSeen = frame.framesSeen;
    w.lastSeen = frame.framesSeen;
    w.last = frame;
    dispatch({
      type: "frame",
      stats: frame.stats,
      points: frame.points,
      aspect: frame.aspect,
      atMs: frame.atMs,
    });
  }, []);
  const onExposure = useCallback(
    (isoRatio: number) => dispatch({ type: "exposure", isoRatio }),
    [],
  );
  const onDiagnostics = useCallback((diagnostics: CameraDiagnostics) => {
    counters.current.diagnostics = diagnostics;
  }, []);
  const scanAnyway = useCallback(() => dispatch({ type: "scanAnyway" }), []);

  // AR scan: the native view reports status, pose and detections.
  const platform = Platform.OS === "ios" ? "ios" : "android";
  const onArStatus = useCallback(
    (status: ArStatus & Omit<ArDebug, "tracking">) => {
      counters.current.ar = {
        tracking: status.tracking,
        lidar: status.lidar,
        planes: status.planes,
        meshTriangles: status.meshTriangles,
        mappedPoints: status.mappedPoints,
        detector: status.detector,
        labels: status.labels,
      };
      dispatch(arFrameEvent(status, platform, Date.now()));
    },
    [platform],
  );
  const onArPose = useCallback(
    (pose: { yaw: number; pitch: number; tracking: string }) =>
      dispatch(arPoseEvent(pose, Date.now())),
    [],
  );
  const onArDetections = useCallback((detections: Detection[]) => {
    setLabels((current) => updateLabels(current, detections, Date.now()));
  }, []);

  return {
    state,
    debug,
    labels,
    onFrame,
    onExposure,
    onDiagnostics,
    onArStatus,
    onArPose,
    onArDetections,
    scanAnyway,
  };
}
