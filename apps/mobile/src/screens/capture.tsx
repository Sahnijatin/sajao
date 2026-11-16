import { Button, GlassSurface, Text, useTheme } from "@sajao/ui";
import { MeshEffect } from "@sajao/ui/effects";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCameraPermission } from "react-native-vision-camera";
import type { GuardrailId, GuardrailStatus } from "@/capture/guardrails";
import { toScreen } from "@/capture/mesh-tracker";
import { ScanCamera } from "@/capture/scan-camera";
import { canFinish } from "@/capture/scan-session";
import { useScanSession } from "@/capture/use-scan-session";

export interface CaptureScreenProps {
  onClose: () => void;
  onDone: () => void;
  onUsePhotos: () => void;
}

const CHIPS: readonly GuardrailId[] = ["light", "motion", "level"];

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

function RoundButton({ label, onPress, on }: { label: string; onPress: () => void; on?: boolean }) {
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
        <Text variant="captionStrong" tone={on ? "primary" : "onDark"}>
          {label.slice(0, 1)}
        </Text>
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
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { spacing, radius } = tokens;
  const insets = useSafeAreaInsets();
  const window = useWindowDimensions();
  const permission = useCameraPermission();
  const [torch, setTorch] = useState(false);
  const { state, onFrame, scanAnyway } = useScanSession(permission.hasPermission);
  const points = useMemo(() => toScreen(state.mesh, window), [state.mesh, window]);
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
      <ScanCamera
        style={StyleSheet.absoluteFill}
        active={!state.pause.paused}
        torch={torch}
        onAnalysed={onFrame}
      />
      <MeshEffect
        style={StyleSheet.absoluteFill}
        width={window.width}
        height={window.height}
        points={points}
        triangles={state.mesh.triangles}
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
          <RoundButton label={t("capture.close")} onPress={onClose} />
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
            </Text>
          </GlassSurface>
          <RoundButton
            label={t("capture.torch")}
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
