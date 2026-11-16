// Hidden scan diagnostics, opened with a triple tap on the camera. Shows
// whether the frame callback runs at all and what the guardrails read, so a
// scan problem on a phone can be told apart in seconds.
import { Text } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import type { ScanState } from "./scan-session";
import type { ScanDebug } from "./use-scan-session";

const round = (value: number, digits = 0) => value.toFixed(digits);

export function scanDebugLines(
  debug: ScanDebug,
  state: ScanState,
  /** Why the AR session could not start, when it could not: the scan then runs in 2D. */
  arStartError: string | null = null,
): [string, string][] {
  const stats = state.frame?.stats;
  return [
    ["cameraFps", round(debug.cameraFps)],
    ["analysedFps", round(debug.analysedFps)],
    ["featurePoints", round(debug.featurePoints)],
    ["meshPoints", round(state.mesh.points.length)],
    ["analysisMs", round(debug.analysisMs)],
    ["dropped", round(debug.diagnostics.dropped)],
    ["waiting", debug.waitingSeconds > 0 ? `${debug.waitingSeconds} s` : "-"],
    ["brightness", stats ? round(stats.brightness) : "-"],
    ["iso", round(state.isoRatio, 2)],
    ["turn", round(state.motion.rotationRate)],
    ["shake", round(state.motion.acceleration, 1)],
    ["roll", round(state.motion.rollDegrees)],
    ["pitch", round(state.motion.pitchDegrees)],
    ["yaw", round(state.pose.yaw)],
    ["gyro", state.hasGyro ? "1" : "0"],
    ["usable", round(state.usableFrames)],
    ["error", debug.diagnostics.lastError ?? "-"],
    ...(arStartError ? ([["arStart", arStartError]] as [string, string][]) : []),
    ...(debug.ar
      ? ([
          ["tracking", debug.ar.tracking],
          ["lidar", debug.ar.lidar ? "1" : "0"],
          ["planes", round(debug.ar.planes)],
          ["meshTriangles", round(debug.ar.meshTriangles)],
          ["mappedPoints", round(debug.ar.mappedPoints)],
          ["detector", debug.ar.detector ? "1" : "0"],
          ["detectorStatus", debug.ar.detectorStatus || "-"],
          ["cameraImage", debug.ar.cameraImage || "-"],
          ["session", debug.ar.session || "-"],
          ["planeStates", debug.ar.planeStates || "-"],
          ["surfaceHits", debug.ar.surfaceHits || "-"],
          ["video", debug.ar.video || "-"],
          ["errors", debug.ar.errors || "-"],
          ["lastError", debug.ar.lastError || "-"],
          ["labels", round(debug.ar.labels)],
          ["detectionsFound", round(debug.ar.detectionsFound)],
          ["detectionsPlaced", round(debug.ar.detectionsPlaced)],
          ["placedBy", debug.ar.placedBy || "-"],
          ["detectorError", debug.ar.detectorError || "-"],
          ["labelsRejected", round(debug.ar.labelsRejected)],
          ["arTurn", round(state.turnRate)],
          ["walls", round(state.surfaces.walls.length)],
          ["samplesAccepted", round(state.surfaces.accepted)],
          ["samplesRejected", round(state.surfaces.rejected)],
        ] as [string, string][])
      : []),
  ];
}

export function DebugOverlay({
  debug,
  state,
  arStartError = null,
}: {
  debug: ScanDebug;
  state: ScanState;
  arStartError?: string | null;
}) {
  const { t } = useTranslation();
  return (
    <View
      testID="scan-debug"
      pointerEvents="none"
      style={{ padding: 8, borderRadius: 8, backgroundColor: "rgba(0, 0, 0, 0.7)", gap: 2 }}
    >
      {scanDebugLines(debug, state, arStartError).map(([key, value]) => (
        <Text key={key} variant="caption" tone="onDark">
          {`${t(`capture.debug.${key}`)}: ${value}`}
        </Text>
      ))}
    </View>
  );
}
