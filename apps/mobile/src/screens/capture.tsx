import { Button, GlassSurface, Text, useTheme } from "@sajao/ui";
import { MeshEffect } from "@sajao/ui/effects";
import { Icon, type IconName } from "@sajao/ui/icons";
import { useKeepAwake } from "expo-keep-awake";
import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCameraPermission } from "react-native-vision-camera";
import { getArCapabilities, getArView } from "../../modules/sajao-ar";
import { shownLabels } from "@/capture/ar/labels";
import { mappedSectors } from "@/capture/coverage";
import { DebugOverlay } from "@/capture/debug-overlay";
import type { GuardrailId, GuardrailStatus } from "@/capture/guardrails";
import { toScreen } from "@/capture/mesh-tracker";
import { MiniMap } from "@/capture/mini-map";
import { ScanCamera } from "@/capture/scan-camera";
import { canFinish, mappedShare } from "@/capture/scan-session";
import { useScanSession } from "@/capture/use-scan-session";

export interface CaptureScreenProps {
  onClose: () => void;
  onDone: () => void;
  onUsePhotos: () => void;
}

const CHIPS: readonly GuardrailId[] = ["light", "motion", "level"];

/** Keeps the screen on while the scan screen is open, on iOS and Android. */
export const SCAN_KEEP_AWAKE_TAG = "sajao-scan";

function StatusChip({ id, status }: { id: GuardrailId; status: GuardrailStatus }) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing, radius } = tokens;
  return (
    <GlassSurface
      tone="dark"
      accessibilityRole="text"
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
        height: 30,
        paddingHorizontal: spacing.lg,
        borderRadius: radius.pill,
      }}
    >
      <View
        style={{
          width: 6,
          height: 6,
          borderRadius: 3,
          backgroundColor: status === "good" ? colors.success : colors.warning,
        }}
      />
      <Text variant="captionStrong" tone="onDark">
        {t(`capture.chips.${id}.${status}`)}
      </Text>
    </GlassSurface>
  );
}

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
          width: 44,
          height: 44,
          borderRadius: tokens.radius.pill,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon name={icon} color={on ? tokens.colors.accent : "#ffffff"} />
      </GlassSurface>
    </Pressable>
  );
}

/**
 * The scan screen: live camera with the scan mesh spreading over what has
 * been mapped, guardrail chips, and a soft pause with a fix when a
 * guardrail fails. There is no room-type picker.
 */
export function CaptureScreen({ onClose, onDone, onUsePhotos }: CaptureScreenProps) {
  // A scan is hands-on but touch-free: without this the screen dims and locks mid-scan.
  useKeepAwake(SCAN_KEEP_AWAKE_TAG);
  const { t } = useTranslation();
  const { tokens, tier, reducedMotion } = useTheme();
  const { spacing, radius } = tokens;
  const insets = useSafeAreaInsets();
  const window = useWindowDimensions();
  const permission = useCameraPermission();
  const [torch, setTorch] = useState(false);
  const {
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
  } = useScanSession(permission.hasPermission);
  // AR-anchored scan where the phone supports it; otherwise the 2D scan.
  const capabilities = useMemo(() => getArCapabilities(), []);
  const ArView = useMemo(() => getArView(), []);
  const [arFailed, setArFailed] = useState(false);
  const arMode = capabilities.arSupported && ArView !== null && !arFailed;
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
  const mapped = useMemo(() => mappedSectors(state.coverage), [state.coverage]);
  const percent = Math.round(mappedShare(state) * 100);
  const [showDebug, setShowDebug] = useState(false);
  const taps = useRef<number[]>([]);
  // Hidden debug overlay: three taps on the camera within a second.
  const onCameraTap = useCallback(() => {
    const now = Date.now();
    taps.current = [...taps.current.filter((at) => now - at < 1000), now];
    if (taps.current.length >= 3) {
      taps.current = [];
      setShowDebug((shown) => !shown);
    }
  }, []);
  const reason = state.pause.reason;
  // Glare has no chip of its own until it is a problem.
  const chips = state.guardrails.glare === "warn" ? [...CHIPS, "glare" as const] : CHIPS;

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
    <View style={{ flex: 1, backgroundColor: "#000000" }}>
      {/* The camera keeps running while paused, so the scan can see the fix and resume. */}
      {arMode && ArView ? (
        <ArView
          style={StyleSheet.absoluteFill}
          active
          torch={torch}
          lite={tier === "low"}
          reducedMotion={reducedMotion}
          labels={labelProps}
          onArStatus={({ nativeEvent }) => {
            // A session that cannot start falls back to the 2D scan.
            if ("error" in nativeEvent) setArFailed(true);
            else onArStatus(nativeEvent);
          }}
          onArPose={({ nativeEvent }) => onArPose(nativeEvent)}
          onArDetections={({ nativeEvent }) =>
            onArDetections(
              (nativeEvent.detections ?? []).map((detection) => ({
                detectorClass: detection.detectorClass,
                score: detection.score,
                world: detection.world ?? null,
                surface: detection.surface,
                gap: detection.gap ?? null,
                range: detection.range ?? null,
              })),
            )
          }
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
          <MeshEffect
            style={StyleSheet.absoluteFill}
            width={window.width}
            height={window.height}
            points={points}
            triangles={state.mesh.triangles}
          />
        </>
      )}
      <Pressable
        testID="scan-camera-area"
        accessible={false}
        style={StyleSheet.absoluteFill}
        onPress={onCameraTap}
      />

      <View
        style={{
          position: "absolute",
          top: insets.top + spacing.md,
          left: spacing.gutter,
          right: spacing.gutter,
          gap: spacing.xl,
        }}
      >
        <View
          style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}
        >
          <RoundButton label={t("capture.close")} icon="close" onPress={onClose} />
          <GlassSurface
            tone="dark"
            style={{
              height: 36,
              paddingHorizontal: spacing.xxl,
              borderRadius: radius.pill,
              justifyContent: "center",
            }}
          >
            <Text variant="meta" tone="onDark" accessibilityRole="header">
              {t("capture.title")}
              <Text variant="meta" tone="onDark" testID="scan-mapped">
                {`  ${t("capture.mapped", { percent })}`}
              </Text>
            </Text>
          </GlassSurface>
          <RoundButton
            label={t("capture.torch")}
            icon={torch ? "torchOn" : "torch"}
            on={torch}
            onPress={() => setTorch((on) => !on)}
          />
        </View>
        <View
          style={{
            flexDirection: "row",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: spacing.md,
          }}
        >
          {chips.map((id) => (
            <StatusChip key={id} id={id} status={state.guardrails[id]} />
          ))}
        </View>
        <View
          style={{
            flexDirection: "row",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          <View style={{ flex: 1 }}>
            {showDebug ? <DebugOverlay debug={debug} state={state} /> : null}
          </View>
          <MiniMap mapped={mapped} yaw={state.pose.yaw} />
        </View>
      </View>

      <GlassSurface
        tone="dark"
        style={{
          position: "absolute",
          left: spacing.md,
          right: spacing.md,
          bottom: insets.bottom + spacing.md,
          padding: spacing.gutter,
          gap: spacing.xl,
          borderRadius: radius.sheet,
        }}
      >
        {state.pause.paused && reason && reason !== "level" ? (
          <>
            <Text variant="captionStrong" tone="onDark">
              {t("capture.pausedTitle")}
            </Text>
            <Text variant="heading" tone="onDark">
              {t(`capture.fix.${reason}.title`)}
            </Text>
            <Text variant="bodySmall" tone="onDark">
              {t(`capture.fix.${reason}.body`)}
            </Text>
            <View style={{ flexDirection: "row", gap: spacing.lg }}>
              <Button
                label={t("capture.scanAnyway")}
                variant="outline"
                style={{ flex: 1 }}
                onPress={scanAnyway}
              />
              {/* The scan resumes by itself once the reading is good again. */}
              <Button
                label={t(`capture.fix.${reason}.fixed`)}
                style={{ flex: 1 }}
                onPress={() => (reason === "light" ? setTorch(true) : undefined)}
              />
            </View>
          </>
        ) : (
          <>
            <Text variant="heading" tone="onDark">
              {t("capture.guideTitle")}
            </Text>
            <Text variant="bodySmall" tone="onDark">
              {t("capture.guideBody")}
            </Text>
            <View style={{ flexDirection: "row", gap: spacing.lg }}>
              <Button
                label={t("capture.usePhotos")}
                variant="outline"
                style={{ flex: 1 }}
                onPress={onUsePhotos}
              />
              <Button
                label={t("capture.done")}
                style={{ flex: 1 }}
                disabled={!canFinish(state)}
                haptic="roomVerified"
                onPress={onDone}
              />
            </View>
          </>
        )}
      </GlassSurface>
    </View>
  );
}
