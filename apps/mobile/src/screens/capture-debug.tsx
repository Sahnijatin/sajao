// Scan diagnostics for builders and testers, shown only with the debug flag
// (three taps on the camera in a development or preview build): the mapped
// share, the guardrail chips, the compass map and the numbers. None of this
// is part of the scan a person sees.
import { GlassSurface, Text, useTheme } from "@sajao/ui";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { mappedSectors } from "@/capture/coverage";
import { DebugOverlay } from "@/capture/debug-overlay";
import type { GuardrailId, GuardrailStatus } from "@/capture/guardrails";
import { meterParts } from "@/capture/coverage-meter";
import { MeterMap } from "@/capture/meter-map";
import { MiniMap } from "@/capture/mini-map";
import { ProgressRing } from "@/capture/progress-ring";
import {
  canFinish,
  isMeter,
  mappedShare,
  type ScanState,
  shouldShowSlowDown,
} from "@/capture/scan-session";
import type { ScanDebug } from "@/capture/use-scan-session";

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
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.lg,
        borderRadius: radius.pill,
      }}
    >
      <View
        style={{
          width: spacing.sm,
          height: spacing.sm,
          borderRadius: radius.pill,
          backgroundColor: status === "good" ? colors.success : colors.warning,
        }}
      />
      <Text variant="captionStrong" tone="onDark">
        {t(`capture.chips.${id}.${status}`)}
      </Text>
    </GlassSurface>
  );
}

export function CaptureDebugLayer({
  state,
  debug,
  arStartError,
  simple,
  top,
}: {
  state: ScanState;
  debug: ScanDebug;
  arStartError: string | null;
  /** The simple scan shows a ring with a number in place of the compass map. */
  simple: boolean;
  /** Distance from the top of the screen, below the close button. */
  top: number;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { spacing } = tokens;
  const mapped = useMemo(() => mappedSectors(state.coverage), [state.coverage]);
  const share = mappedShare(state);
  // Glare has no chip of its own until it is a problem.
  const chips = state.guardrails.glare === "warn" ? [...CHIPS, "glare" as const] : CHIPS;
  // AR scan: frames rejected for turning fast or blur also read as "slow down".
  const slowDown = shouldShowSlowDown(state);
  const chipStatus = (id: GuardrailId): GuardrailStatus =>
    id === "motion" && slowDown ? "warn" : state.guardrails[id];
  return (
    <View
      testID="scan-debug-layer"
      pointerEvents="none"
      style={{
        position: "absolute",
        top,
        left: spacing.gutter,
        right: spacing.gutter,
        gap: spacing.md,
      }}
    >
      <Text variant="meta" tone="onDark" testID="scan-mapped">
        {t("capture.mapped", { percent: Math.round(share * 100) })}
      </Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
        {chips.map((id) => (
          <StatusChip key={id} id={id} status={chipStatus(id)} />
        ))}
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1 }}>
          <DebugOverlay debug={debug} state={state} arStartError={arStartError} />
        </View>
        {isMeter(state) ? (
          // The coverage meter: its two-part ring and its map of where has been walked.
          <View style={{ alignItems: "center", gap: spacing.sm }}>
            <ProgressRing
              progress={share}
              ready={canFinish(state)}
              parts={meterParts(state.meter)}
            />
            <MeterMap meter={state.meter} position={state.position} yaw={state.pose.yaw} />
          </View>
        ) : simple ? (
          <ProgressRing progress={share} ready={canFinish(state)} />
        ) : (
          <MiniMap mapped={mapped} yaw={state.pose.yaw} />
        )}
      </View>
    </View>
  );
}
