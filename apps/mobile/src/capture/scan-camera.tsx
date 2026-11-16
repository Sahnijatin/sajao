// The camera for a scan: live preview plus on-device analysis of a small
// grayscale copy of some frames. This file is the only place that touches
// the camera library; everything it reports is plain data.
//
// Not yet run on a device: it compiles against the installed camera
// library, and needs a development build on a phone to be verified.
import type { StyleProp, ViewStyle } from "react-native";
import { Camera, useCameraDevice, useFrameOutput } from "react-native-vision-camera";
import { useSharedValue } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { downsampleLuma } from "./downsample";
import { detectFeaturePoints, type FeaturePoint } from "./feature-points";
import { type FrameStats, frameStats } from "./frame-stats";

/** Analyse about eight frames a second; the preview itself stays at full rate. */
const ANALYSIS_INTERVAL_MS = 120;

export interface AnalysedFrame {
  stats: FrameStats;
  points: FeaturePoint[];
  elapsedMs: number;
}

export interface ScanCameraProps {
  active: boolean;
  torch: boolean;
  /** Called on the React thread with each analysed frame. */
  onAnalysed: (frame: AnalysedFrame) => void;
  style?: StyleProp<ViewStyle>;
}

export function ScanCamera({ active, torch, onAnalysed, style }: ScanCameraProps) {
  const device = useCameraDevice("back");
  // A shared value, because the frame callback runs on the camera thread.
  const lastMs = useSharedValue(0);

  const frameOutput = useFrameOutput({
    pixelFormat: "yuv",
    onFrame(frame) {
      "worklet";
      try {
        const nowMs = frame.timestamp / 1_000_000;
        const previousMs = lastMs.get();
        const elapsedMs = nowMs - previousMs;
        if (previousMs !== 0 && elapsedMs < ANALYSIS_INTERVAL_MS) return;
        const luma = frame.getPlanes()[0];
        if (!luma) return;
        const gray = downsampleLuma(luma.getPixelBuffer(), {
          width: luma.width,
          height: luma.height,
          bytesPerRow: luma.bytesPerRow,
        });
        const analysed: AnalysedFrame = {
          stats: frameStats(gray),
          points: detectFeaturePoints(gray),
          elapsedMs: previousMs === 0 ? ANALYSIS_INTERVAL_MS : elapsedMs,
        };
        lastMs.set(nowMs);
        scheduleOnRN(onAnalysed, analysed);
      } finally {
        // Always release the frame, or the camera stalls.
        frame.dispose();
      }
    },
  });

  if (!device) return null;
  return (
    <Camera
      style={style}
      device={device}
      isActive={active}
      outputs={[frameOutput]}
      torchMode={torch ? "on" : "off"}
    />
  );
}
