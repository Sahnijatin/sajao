import { Button, GlassSurface, motion, playHaptic, Text, touchTarget, useTheme } from "@sajao/ui";
import { MeshEffect } from "@sajao/ui/effects";
import { Icon, type IconName } from "@sajao/ui/icons";
import { useKeepAwake } from "expo-keep-awake";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";
import Animated, { cubicBezier, Easing, FadeIn } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCameraPermission } from "react-native-vision-camera";
import { getArCapabilities, getArView } from "../../modules/sajao-ar";
import { shownLabels } from "@/capture/ar/labels";
import { meterMissing } from "@/capture/coverage-meter";
import { MeterMap } from "@/capture/meter-map";
import { NoArNotice } from "@/capture/no-ar-notice";
import { toScreen } from "@/capture/mesh-tracker";
import { imuReading } from "@/capture/package/imu";
import type { LocalCapture } from "@/capture/package/native-capture";
import type { CaptureDeviceInfo } from "@/capture/package/upload-capture";
import { useCaptureRecorder } from "@/capture/package/use-capture-recorder";
import type { RawMotion } from "@/capture/pose";
import { ScanCamera } from "@/capture/scan-camera";
import { canFinish, canFinishEarly, isMeter, isSimple, mappedShare } from "@/capture/scan-session";
import { useScanSession } from "@/capture/use-scan-session";
import { ScanInstruction } from "@/components/scan-instruction";
import { ScanRing } from "@/components/scan-ring";
import { previewScreensEnabled } from "@/preview-screens";
import { useCaptureStore } from "@/state/capture";
import { CaptureDebugLayer } from "./capture-debug";
import { coverageStep, scanInstruction, shouldTick } from "./capture-guide";

export interface CaptureScreenProps {
  onClose: () => void;
  onDone: () => void;
  onUsePhotos: () => void;
  /** The finished scan, ready to upload; called before onDone. */
  onCaptured?: (capture: LocalCapture, device: CaptureDeviceInfo) => void;
}

/** The round glass buttons at the top: one touch target. */
const ROUND_BUTTON = touchTarget;

/** Keeps the screen on while the scan screen is open, on iOS and Android. */
export const SCAN_KEEP_AWAKE_TAG = "sajao-scan";

function RoundButton({
  label,
  icon,
  onPress,
  on,
}: {
  label: string;
  icon: IconName;
  onPress: () => void;
  on?: boolean;
}) {
  const { tokens } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={on === undefined ? {} : { selected: on }}
      onPress={onPress}
    >
      <GlassSurface
        tone={on ? "light" : "dark"}
        style={{
          width: ROUND_BUTTON,
          height: ROUND_BUTTON,
          borderRadius: tokens.radius.pill,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon name={icon} color={on ? tokens.colors.accent : tokens.glass.dark.text} />
      </GlassSurface>
    </Pressable>
  );
}

/** The ring with Done inside it. */
const RING_SIZE = 88;
/** Space between the ring and the button inside it. */
const RING_GAP = 8;
const NO_LABELS: never[] = [];
const pressEasing = cubicBezier(...motion.press.bezier);

/**
 * The scan's progress and its way out, in one control: a thin ring that
 * fills as the room is covered, and Done inside it once there is enough.
 */
function DoneRing({
  progress,
  ready,
  busy,
  onPress,
}: {
  progress: number;
  ready: boolean;
  busy: boolean;
  onPress: () => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const [pressed, setPressed] = useState(false);
  const enabled = ready && !busy;
  const percent = Math.round(Math.min(1, Math.max(0, progress)) * 100);
  const fade = duration(motion.ease.durationMs);
  return (
    <Pressable
      testID="scan-done"
      accessibilityRole={ready ? "button" : "progressbar"}
      accessibilityLabel={ready ? t("capture.done") : t("capture.progress")}
      accessibilityValue={{ min: 0, max: 100, now: percent }}
      accessibilityState={{ disabled: !enabled }}
      disabled={!enabled}
      pressRetentionOffset={16}
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
      onPress={() => {
        void playHaptic("roomVerified");
        onPress();
      }}
      style={{
        width: RING_SIZE,
        height: RING_SIZE,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <ScanRing progress={progress} ready={ready} size={RING_SIZE} />
      <Animated.View
        style={{
          width: RING_SIZE - RING_GAP * 2,
          height: RING_SIZE - RING_GAP * 2,
          borderRadius: tokens.radius.pill,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: ready ? tokens.colors.surface : tokens.glass.dark.fill,
          opacity: busy ? 0.4 : 1,
          transform: [{ scale: pressed ? motion.press.scale : 1 }],
          transitionProperty: "transform",
          transitionDuration: duration(motion.press.durationMs),
          transitionTimingFunction: pressEasing,
        }}
      >
        {ready ? (
          <Animated.View
            entering={
              fade > 0
                ? FadeIn.duration(fade).easing(Easing.bezier(...motion.ease.bezier))
                : undefined
            }
          >
            <Text variant="label">{t("capture.done")}</Text>
          </Animated.View>
        ) : null}
      </Animated.View>
    </Pressable>
  );
}

/**
 * The scan screen: the camera, full screen, with one thin ring and one plain
 * instruction at a time. Coverage ticks softly under your fingers as it
 * grows. A nudge appears only when something needs fixing. Chips, the
 * compass map, live labels and the scan mesh are diagnostics: they show only
 * with the debug flag. There is no room-type picker.
 */
export function CaptureScreen({ onClose, onDone, onUsePhotos, onCaptured }: CaptureScreenProps) {
  // A scan is hands-on but touch-free: without this the screen dims and locks mid-scan.
  useKeepAwake(SCAN_KEEP_AWAKE_TAG);
  const { t } = useTranslation();
  const { tokens, tier, reducedMotion } = useTheme();
  const { spacing } = tokens;
  const insets = useSafeAreaInsets();
  const window = useWindowDimensions();
  const permission = useCameraPermission();
  const [torch, setTorch] = useState(false);
  // AR-anchored scan where the phone supports it; otherwise the 2D scan.
  const capabilities = useMemo(() => getArCapabilities(), []);
  // The capture package: video, keyframes with poses, depth, planes, detections, sensor log.
  const capture = useCaptureRecorder({
    tracking: capabilities.platform === "ios" ? "arkit" : "arcore",
    lidar: capabilities.lidar,
    depth: false,
  });
  const captureSensor = capture.onSensor;
  // Motion sensor readings go into the package's sensor log in every mode.
  const onImu = useCallback(
    (reading: RawMotion) => {
      const line = imuReading(reading);
      if (line) captureSensor(line);
    },
    [captureSensor],
  );
  const {
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
  } = useScanSession(permission.hasPermission, onImu);
  const ArView = useMemo(() => getArView(), []);
  // The native error when the AR session could not start; the 2D scan takes over.
  const [arStartError, setArStartError] = useState<string | null>(null);
  const arMode = capabilities.arSupported && ArView !== null && arStartError === null;
  const [finishing, setFinishing] = useState(false);
  const setMissing = useCaptureStore((store) => store.setMissing);
  const finishScan = useCallback(async () => {
    setFinishing(true);
    if (arMode) {
      // What the meter still wanted, for the review to name after "Finish anyway".
      setMissing(isMeter(state) ? meterMissing(state.meter) : null);
      const local = await capture.finish();
      onCaptured?.(local, {
        platform: capabilities.platform === "ios" ? "ios" : "android",
        tier: tier === "low" ? "low" : "standard",
        has_ar: true,
      });
    }
    onDone();
  }, [arMode, capabilities.platform, capture, onCaptured, onDone, setMissing, state, tier]);
  const labelProps = useMemo(
    () =>
      shownLabels(labels).map((label) => ({
        id: label.id,
        text: t(`capture.labels.${label.kind}`),
        x: label.x,
        y: label.y,
        z: label.z,
      })),
    [labels, t],
  );
  const aspect = state.frame?.aspect ?? 9 / 16;
  const points = useMemo(() => toScreen(state.mesh, window, aspect), [state.mesh, window, aspect]);
  const share = mappedShare(state);
  const ready = canFinish(state);
  const simple = arMode && isSimple(state);
  // Where AR gives positions the coverage meter decides Done, in both scan modes.
  const meter = arMode && isMeter(state);
  const [showDebug, setShowDebug] = useState(false);
  const taps = useRef<number[]>([]);
  // The debug flag: three taps on the camera within a second, in development
  // and preview builds only. The store build has no way to switch it on.
  const onCameraTap = useCallback(() => {
    if (!previewScreensEnabled()) return;
    const now = Date.now();
    taps.current = [...taps.current.filter((at) => now - at < 1000), now];
    if (taps.current.length >= 3) {
      taps.current = [];
      setShowDebug((shown) => !shown);
    }
  }, []);
  const pausedFor = state.pause.paused ? state.pause.reason : null;
  const instruction = scanInstruction({ pausedFor, hint, share, ready });
  const instructionText =
    instruction.id === "walkAround" && instruction.kind
      ? t("capture.guide.walkAround", {
          object: t(`capture.labels.${instruction.kind}`).toLowerCase(),
        })
      : t(`capture.guide.${instruction.id}`);

  // A light tick each time coverage passes another tenth, and one more when
  // Done becomes ready. The ring shows the same thing: haptics never stand alone.
  const step = useRef(0);
  useEffect(() => {
    if (!shouldTick(step.current, share)) return;
    step.current = coverageStep(share);
    // The coverage meter is felt sector by sector by the scan session itself.
    if (meter) return;
    void playHaptic("cornerCaptured");
  }, [share, meter]);
  const wasReady = useRef(false);
  useEffect(() => {
    if (ready && !wasReady.current) void playHaptic("levelReached");
    wasReady.current = ready;
  }, [ready]);

  // A phone that cannot run AR cannot measure the room: it goes to photos
  // with a friendly note, before any camera permission is asked for.
  if (!arMode) return <NoArNotice onUsePhotos={onUsePhotos} onClose={onClose} />;

  if (!permission.hasPermission) {
    return (
      <View
        style={{
          flex: 1,
          justifyContent: "center",
          gap: spacing.gutter,
          padding: spacing.gutter,
          backgroundColor: tokens.colors.canvas,
        }}
      >
        <Text variant="title">{t("capture.permissionTitle")}</Text>
        <Text tone="secondary">{t("capture.permissionBody")}</Text>
        {permission.canRequestPermission ? (
          <Button
            label={t("capture.permissionAllow")}
            onPress={() => void permission.requestPermission()}
          />
        ) : null}
        <Button label={t("capture.usePhotos")} variant="outline" onPress={onUsePhotos} />
        <Button label={t("capture.close")} variant="ghost" size="small" onPress={onClose} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: tokens.colors.ink }}>
      {/* The camera keeps running while paused, so the scan can see the fix and resume. */}
      {arMode && ArView ? (
        <ArView
          ref={capture.viewRef}
          captureId={capture.captureId}
          capturePaused={capture.capturePaused}
          onArKeyframe={({ nativeEvent }) => capture.onKeyframe(nativeEvent)}
          style={StyleSheet.absoluteFill}
          active
          torch={torch}
          lite={tier === "low"}
          reducedMotion={reducedMotion}
          // The mesh, planes and live labels are diagnostics: the scan shows
          // the camera image only, unless the debug flag is on.
          overlay={showDebug}
          labels={showDebug ? labelProps : NO_LABELS}
          onArStatus={({ nativeEvent }) => {
            // A session that cannot start falls back to the 2D scan.
            if ("error" in nativeEvent) setArStartError(String(nativeEvent.error) || "unknown");
            else onArStatus(nativeEvent);
          }}
          onArPose={({ nativeEvent }) => {
            onArPose(nativeEvent);
            capture.onSensor({
              source: "ar_pose",
              x: nativeEvent.x,
              y: nativeEvent.y,
              z: nativeEvent.z,
              yaw: nativeEvent.yaw,
              pitch: nativeEvent.pitch,
              tracking: nativeEvent.tracking,
            });
          }}
          onArSurfaces={({ nativeEvent }) =>
            onArSurfaces({
              sharpness: nativeEvent.sharpness,
              hits: nativeEvent.hits ?? [],
              floorY: nativeEvent.floorY ?? null,
            })
          }
          onArDetections={({ nativeEvent }) => {
            const detections = nativeEvent.detections ?? [];
            // Every detection goes into the package; the server decides what it means.
            capture.onDetections(
              detections.map((detection) => ({
                detectorClass: detection.detectorClass,
                score: detection.score,
                world: detection.world ?? null,
              })),
            );
            onArDetections(
              detections.map((detection) => ({
                detectorClass: detection.detectorClass,
                score: detection.score,
                world: detection.world ?? null,
                surface: detection.surface,
                gap: detection.gap ?? null,
                range: detection.range ?? null,
                placedBy: detection.placedBy,
                box: detection.box ?? null,
              })),
            );
          }}
        />
      ) : (
        <>
          <ScanCamera
            style={StyleSheet.absoluteFill}
            active
            torch={torch}
            onAnalysed={onFrame}
            onExposure={onExposure}
            onDiagnostics={onDiagnostics}
          />
          {showDebug ? (
            <MeshEffect
              style={StyleSheet.absoluteFill}
              width={window.width}
              height={window.height}
              points={points}
              triangles={state.mesh.triangles}
            />
          ) : null}
        </>
      )}
      <Pressable
        testID="scan-camera-area"
        accessible={false}
        style={StyleSheet.absoluteFill}
        onPress={onCameraTap}
      />

      {/* Top: the way out, and the torch only when it can help. */}
      <View
        pointerEvents="box-none"
        style={{
          position: "absolute",
          top: insets.top + spacing.md,
          left: spacing.gutter,
          right: spacing.gutter,
          flexDirection: "row",
          justifyContent: "space-between",
        }}
      >
        <RoundButton label={t("capture.close")} icon="close" onPress={onClose} />
        {torch || pausedFor === "light" || showDebug ? (
          <RoundButton
            label={t("capture.torch")}
            icon={torch ? "torchOn" : "torch"}
            on={torch}
            onPress={() => setTorch((on) => !on)}
          />
        ) : null}
      </View>

      {showDebug ? (
        <CaptureDebugLayer
          state={state}
          debug={debug}
          arStartError={arStartError}
          simple={simple}
          top={insets.top + spacing.md + ROUND_BUTTON + spacing.md}
        />
      ) : null}

      {/* Bottom: one instruction, a way on when the scan is paused, and the ring. */}
      <View
        pointerEvents="box-none"
        style={{
          position: "absolute",
          left: spacing.gutter,
          right: spacing.gutter,
          bottom: insets.bottom + spacing.sheetBottom,
          alignItems: "center",
          gap: spacing.gutter,
        }}
      >
        {/* "One more spot, over there" needs a there: the meter's map shows it, for that step only. */}
        {meter && instruction.id === "oneMoreSpot" ? (
          <MeterMap meter={state.meter} position={state.position} yaw={state.pose.yaw} />
        ) : null}
        <ScanInstruction
          id={`${instruction.id}:${instruction.kind ?? ""}`}
          text={instructionText}
        />
        {instruction.tone === "fix" ? (
          // The scan resumes by itself once the reading is good again.
          <View style={{ flexDirection: "row", gap: spacing.lg }}>
            {pausedFor === "light" && !torch ? (
              <Button
                label={t("capture.torchOn")}
                variant="outline"
                size="small"
                onPress={() => setTorch(true)}
              />
            ) : null}
            <Button
              label={t("capture.keepGoing")}
              variant="outline"
              size="small"
              onPress={scanAnyway}
            />
          </View>
        ) : null}
        {canFinishEarly(state) && !ready && !finishing ? (
          // Coverage has not moved for a minute: never trap the person in the scan.
          <Button
            label={t("capture.finishAnyway")}
            variant="outline"
            size="small"
            onPress={() => void finishScan()}
          />
        ) : null}
        <DoneRing
          progress={share}
          ready={ready}
          busy={finishing}
          onPress={() => void finishScan()}
        />
      </View>
    </View>
  );
}
