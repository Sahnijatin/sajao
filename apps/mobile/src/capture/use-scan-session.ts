import { useTheme } from "@sajao/ui";
import { DeviceMotion } from "expo-sensors";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { Platform } from "react-native";
import { arCountersOf, type ArFrameCounters, arFrameRates, NO_AR_COUNTERS } from "./ar/ar-debug";
import type { ArStatusEvent } from "../../modules/sajao-ar";
import { arFrameEvent, arPoseEvent } from "./ar/ar-events";
import {
  currentHint,
  type Hint,
  isCutOff,
  updateViews,
  type ViewBins,
  walkAroundTarget,
} from "./ar/guidance";
import {
  type Detection,
  EMPTY_LABELS,
  labelKindOf,
  type LabelState,
  MIN_SCORE,
  trackedObjects,
  updateLabels,
} from "./ar/labels";
import type { SurfaceHit } from "./ar/surface-coverage";
import { motionSample } from "./pose";
import type { AnalysedFrame, CameraDiagnostics } from "./scan-camera";
import { canFinish, INITIAL_SCAN, mappedShare, scanReducer } from "./scan-session";

const MOTION_INTERVAL_MS = 100;
const DEBUG_WINDOW_MS = 1000;
/** "Step back" stays up this long after the last cut-off large object. */
const STEP_BACK_MS = 2500;

/** Numbers for the hidden debug overlay, refreshed about once a second. */
export interface ScanDebug {
  /** Camera frames per second: the frame callback's, or the AR session's during the AR scan. */
  cameraFps: number;
  /** Frames analysed per second: by the 2D scan, or by the detector during the AR scan. */
  analysedFps: number;
  /** Feature points in the latest analysed frame. */
  featurePoints: number;
  /** Time to analyse one frame: the 2D scan's, or one detector run during the AR scan. */
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
  featurePoints: number;
  /** Detections returned so far, and how many were placed in the room. */
  detectionsFound: number;
  detectionsPlaced: number;
  /** Placed detections by how they were placed. */
  placedBy: string;
  /** Detector load and self-test result. */
  detectorStatus: string;
  cameraImage: string;
  planeStates: string;
  surfaceHits: string;
  /** Why the detector failed to load; empty when it loaded. */
  detectorError: string;
  /** Detector sightings dropped as a wall, a door or bare floor. */
  labelsRejected: number;
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
    arCounters: NO_AR_COUNTERS as ArFrameCounters,
    arWindowStart: NO_AR_COUNTERS as ArFrameCounters,
    labelsRejected: 0,
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
      const waiting = Math.round((now - opened) / 1000);
      if (w.ar) {
        // AR scan: ARKit or ARCore owns the camera, so its counters are the frames.
        const rates = arFrameRates(w.arWindowStart, w.arCounters, seconds);
        setDebug({
          cameraFps: rates.cameraFps,
          analysedFps: rates.detectorFps,
          featurePoints: w.ar.featurePoints,
          analysisMs: rates.detectorMs,
          waitingSeconds: w.arCounters.frames > 0 ? 0 : waiting,
          diagnostics: { ...w.diagnostics, dropped: rates.detectorSkipped },
          ar: w.ar,
        });
        w.arWindowStart = w.arCounters;
      } else {
        setDebug({
          cameraFps: Math.round(seen / seconds),
          analysedFps: Math.round(w.analysed / seconds),
          featurePoints: w.last?.points.length ?? 0,
          analysisMs: w.last?.analysisMs ?? 0,
          waitingSeconds: w.last ? 0 : waiting,
          diagnostics: w.diagnostics,
          ar: null,
        });
      }
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
    (
      // The native view's status event; older builds leave out the newer fields.
      status: ArStatusEvent,
    ) => {
      counters.current.arCounters = arCountersOf(status);
      counters.current.ar = {
        tracking: status.tracking,
        lidar: status.lidar,
        planes: status.planes,
        meshTriangles: status.meshTriangles,
        mappedPoints: status.mappedPoints,
        detector: status.detector,
        labels: status.labels,
        featurePoints: status.featurePoints,
        detectionsFound: status.detectionsFound ?? 0,
        detectionsPlaced: status.detectionsPlaced ?? 0,
        placedBy: status.placedBy ?? "",
        detectorError: status.detectorError ?? "",
        detectorStatus: status.detectorStatus ?? "",
        cameraImage: status.cameraImage ?? "",
        planeStates: status.planeStates ?? "",
        surfaceHits: status.surfaceHits ?? "",
        labelsRejected: counters.current.labelsRejected,
      };
      dispatch(arFrameEvent(status, platform, Date.now()));
    },
    [platform],
  );
  // Capture guidance: which directions each large object has been seen
  // from, and when a large object last filled the frame edge to edge.
  const views = useRef<ViewBins>({});
  const labelsRef = useRef(labels);
  labelsRef.current = labels;
  const [stepBackUntil, setStepBackUntil] = useState(0);
  const onArPose = useCallback(
    (pose: { yaw: number; pitch: number; tracking: string; x?: number; z?: number }) => {
      const event = arPoseEvent(pose, Date.now());
      if (event.position && event.tracking === "normal") {
        views.current = updateViews(
          views.current,
          trackedObjects(labelsRef.current),
          event.position,
        );
      }
      dispatch(event);
    },
    [],
  );
  const onArSurfaces = useCallback(
    (sample: { sharpness: number; hits: readonly SurfaceHit[]; floorY?: number | null }) =>
      dispatch({ type: "arSurfaces", ...sample, atMs: Date.now() }),
    [],
  );
  const onArDetections = useCallback((detections: Detection[]) => {
    const now = Date.now();
    setLabels((current) => updateLabels(current, detections, now));
    const cutOff = detections.some(
      (d) => d.score >= MIN_SCORE && labelKindOf(d.detectorClass) && d.box && isCutOff(d.box),
    );
    if (cutOff) setStepBackUntil(now + STEP_BACK_MS);
  }, []);
  const hint: Hint = currentHint({
    outside: state.doorway.outside,
    stepBack: Date.now() < stepBackUntil,
    walkAround: walkAroundTarget(trackedObjects(labels), views.current, mappedShare(state)),
    coverMore: state.surfacesSeen && canFinish(state) && mappedShare(state) < 1,
  });
  useEffect(() => {
    counters.current.labelsRejected = labels.rejected;
  }, [labels.rejected]);

  return {
    state,
    debug,
    labels,
    hint,
    onFrame,
    onExposure,
    onDiagnostics,
    onArStatus,
    onArPose,
    onArDetections,
    onArSurfaces,
    scanAnyway,
  };
}
