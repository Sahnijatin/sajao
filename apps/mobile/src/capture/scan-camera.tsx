// The camera for a scan: live preview plus on-device analysis of a small
// grayscale copy of some frames. This file is the only place that touches
// the camera library; everything it reports is plain data.
import { useCallback, useEffect, useRef } from "react";
import type { StyleProp, ViewStyle } from "react-native";
import {
  Camera,
  type CameraRef,
  type Frame,
  useCameraDevice,
  useFrameOutput,
} from "react-native-vision-camera";
import { useSharedValue } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { downsampleLuma } from "./downsample";
import { detectFeaturePoints, type FeaturePoint } from "./feature-points";
import { type FrameStats, frameStats } from "./frame-stats";
import { type FrameOrientation, uprightAspect, uprightPoint } from "./orientation";

/**
 * Analyse about twelve frames a second; the preview itself stays at full
 * rate. Timed with the wall clock in the frame callback: frame timestamps
 * are in seconds on iOS and nanoseconds on Android, so they are not used.
 */
const ANALYSIS_INTERVAL_MS = 80;
/** How often the camera's ISO is read for the light check. */
const EXPOSURE_POLL_MS = 500;

export interface AnalysedFrame {
  stats: FrameStats;
  /** Feature points in the upright frame, 0 to 1 on both axes. */
  points: FeaturePoint[];
  /** Width over height of the upright frame. */
  aspect: number;
  /** Wall-clock time the frame was analysed, ms. */
  atMs: number;
  /** Every frame the callback has received so far, analysed or not. */
  framesSeen: number;
  /** Time spent analysing this frame, ms. */
  analysisMs: number;
}

export interface CameraDiagnostics {
  /** Frames the camera dropped because the callback was busy. */
  dropped: number;
  /** The last error thrown inside the frame callback, if any. */
  lastError: string | null;
}

export interface ScanCameraProps {
  active: boolean;
  torch: boolean;
  /** Called on the React thread with each analysed frame. */
  onAnalysed: (frame: AnalysedFrame) => void;
  /** Called with the camera's ISO as a share of its range, 0 to 1. */
  onExposure?: (isoRatio: number) => void;
  /** Called when a frame is dropped or the frame callback fails. */
  onDiagnostics?: (diagnostics: CameraDiagnostics) => void;
  style?: StyleProp<ViewStyle>;
}

export function ScanCamera({
  active,
  torch,
  onAnalysed,
  onExposure,
  onDiagnostics,
  style,
}: ScanCameraProps) {
  const device = useCameraDevice("back");
  const camera = useRef<CameraRef>(null);
  // Shared values, because the frame callback runs on the camera thread.
  const lastMs = useSharedValue(0);
  const framesSeen = useSharedValue(0);
  const diagnostics = useRef<CameraDiagnostics>({ dropped: 0, lastError: null });

  const report = useRef(onDiagnostics);
  report.current = onDiagnostics;
  const onError = useCallback((message: string) => {
    diagnostics.current = { ...diagnostics.current, lastError: message };
    report.current?.(diagnostics.current);
  }, []);
  const onFrameDropped = useCallback(() => {
    diagnostics.current = { ...diagnostics.current, dropped: diagnostics.current.dropped + 1 };
    report.current?.(diagnostics.current);
  }, []);

  // Kept stable so the camera does not re-install the callback on every render.
  const onFrame = useCallback(
    (frame: Frame) => {
      "worklet";
      try {
        framesSeen.set(framesSeen.get() + 1);
        const startMs = Date.now();
        if (startMs - lastMs.get() < ANALYSIS_INTERVAL_MS) return;
        lastMs.set(startMs);
        const luma = frame.getPlanes()[0];
        if (!luma) return;
        const gray = downsampleLuma(luma.getPixelBuffer(), {
          width: luma.width,
          height: luma.height,
          bytesPerRow: luma.bytesPerRow,
        });
        const orientation = frame.orientation as FrameOrientation;
        const mirrored = frame.isMirrored;
        const points = detectFeaturePoints(gray).map((point) => {
          const upright = uprightPoint(point.x, point.y, orientation, mirrored);
          return { x: upright.x, y: upright.y, strength: point.strength };
        });
        const analysed: AnalysedFrame = {
          stats: frameStats(gray),
          points,
          aspect: uprightAspect(luma.width, luma.height, orientation),
          atMs: startMs,
          framesSeen: framesSeen.get(),
          analysisMs: Date.now() - startMs,
        };
        scheduleOnRN(onAnalysed, analysed);
      } catch (error) {
        scheduleOnRN(onError, String(error));
      } finally {
        // Always release the frame, or the camera stalls.
        frame.dispose();
      }
    },
    [framesSeen, lastMs, onAnalysed, onError],
  );

  const frameOutput = useFrameOutput({ pixelFormat: "yuv", onFrame, onFrameDropped });

  // Auto exposure brightens a dark room's picture, so the ISO it needs is
  // read too: near the camera's maximum means the room is dim.
  useEffect(() => {
    if (!active || !onExposure) return;
    const timer = setInterval(() => {
      try {
        const controller = camera.current?.controller;
        if (!controller) return;
        const range = controller.maxISO - controller.minISO;
        if (!(range > 0) || !Number.isFinite(controller.iso)) return;
        onExposure(Math.min(1, Math.max(0, (controller.iso - controller.minISO) / range)));
      } catch {
        // Not every camera reports ISO; brightness alone still works.
      }
    }, EXPOSURE_POLL_MS);
    return () => clearInterval(timer);
  }, [active, onExposure]);

  if (!device) return null;
  return (
    <Camera
      ref={camera}
      style={style}
      device={device}
      isActive={active}
      outputs={[frameOutput]}
      torchMode={torch ? "on" : "off"}
      resizeMode="cover"
    />
  );
}
