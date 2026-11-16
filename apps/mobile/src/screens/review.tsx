// Review, between the scan and the upload: what the scan covered, what is
// missing, a rough size, and two ways on. It sits over the scan while the
// scan is still open, so "Rescan this part" carries on the same scan and
// nothing is uploaded until "Looks good".
import { Button, motion, playHaptic, Text, useTheme } from "@sajao/ui";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { BackHandler, StyleSheet, View } from "react-native";
import Animated, { Easing, FadeIn, SlideInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSettings } from "@/state/settings";
import { formatLength } from "@/utils/format-length";
import type { ScanSummary } from "./review-summary";

export interface ReviewProps {
  summary: ScanSummary;
  /** The upload is starting. */
  busy: boolean;
  /** Back to the same scan. */
  onRescan: () => void;
  /** Confirm: this is what starts the upload. */
  onConfirm: () => void;
}

function Row({ title, children }: { title: string; children: React.ReactNode }) {
  const { tokens } = useTheme();
  return (
    <View style={{ gap: tokens.spacing.xs }}>
      <Text variant="captionStrong" tone="tertiary">
        {title}
      </Text>
      {children}
    </View>
  );
}

export function Review({ summary, busy, onRescan, onConfirm }: ReviewProps) {
  const { t } = useTranslation();
  const { tokens, tier, duration } = useTheme();
  const { colors, spacing, radius } = tokens;
  const insets = useSafeAreaInsets();
  const units = useSettings((state) => state.units);
  const percent = Math.round(summary.share * 100);
  const complete = summary.missing.length === 0;

  // Android back returns to the scan, like "Rescan this part".
  useEffect(() => {
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      onRescan();
      return true;
    });
    return () => subscription.remove();
  }, [onRescan]);

  const slide = duration(motion.ease.durationMs);
  const easing = Easing.bezier(...motion.ease.bezier);
  return (
    <View testID="scan-review" style={StyleSheet.absoluteFill} pointerEvents="box-none">
      {/* The scan stays in view above the sheet: a glimpse of the room we got. */}
      <Animated.View
        entering={slide > 0 ? FadeIn.duration(slide).easing(easing) : undefined}
        style={[StyleSheet.absoluteFill, { backgroundColor: tokens.glass.dark.fill }]}
      />
      <Animated.View
        entering={slide > 0 ? SlideInDown.duration(slide).easing(easing) : undefined}
        accessibilityViewIsModal
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          padding: spacing.gutter,
          paddingTop: spacing.sheetBottom,
          paddingBottom: insets.bottom + spacing.sheetBottom,
          gap: spacing.sheetBottom,
          backgroundColor: colors.surface,
          borderTopLeftRadius: radius.sheet,
          borderTopRightRadius: radius.sheet,
          borderCurve: "continuous",
          boxShadow: tokens.shadows[tier].sheet,
        }}
      >
        <Text variant="title" accessibilityRole="header">
          {t(complete ? "review.titleComplete" : "review.titleMissing")}
        </Text>

        <View style={{ gap: spacing.md }}>
          <View
            accessible
            accessibilityRole="progressbar"
            accessibilityLabel={t("review.covered", { percent })}
            accessibilityValue={{ min: 0, max: 100, now: percent }}
            style={{
              height: spacing.sm,
              borderRadius: radius.pill,
              backgroundColor: colors.sand,
              overflow: "hidden",
            }}
          >
            <View
              style={{
                width: `${percent}%`,
                height: "100%",
                borderRadius: radius.pill,
                backgroundColor: complete ? colors.success : colors.accent,
              }}
            />
          </View>
          <Text variant="bodyStrong">{t("review.covered", { percent })}</Text>
        </View>

        <Row title={t("review.missingTitle")}>
          {complete ? (
            <Text tone="secondary">{t("review.nothingMissing")}</Text>
          ) : (
            summary.missing.map((area) => (
              <View
                key={area}
                testID={`review-missing-${area}`}
                style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}
              >
                <View
                  style={{
                    width: spacing.sm,
                    height: spacing.sm,
                    borderRadius: radius.pill,
                    backgroundColor: colors.warning,
                  }}
                />
                <Text>{t(`review.missing.${area}`)}</Text>
              </View>
            ))
          )}
        </Row>

        <Row title={t("review.sizeTitle")}>
          <Text tone={summary.size ? "primary" : "secondary"} selectable>
            {summary.size
              ? t("review.size", {
                  long: formatLength(summary.size.longM, units, t),
                  short: formatLength(summary.size.shortM, units, t),
                })
              : t("review.sizeLater")}
          </Text>
        </Row>

        <View style={{ flexDirection: "row", gap: spacing.lg }}>
          <Button
            label={t(complete ? "review.scanMore" : "review.rescan")}
            variant="outline"
            style={{ flex: 1 }}
            disabled={busy}
            onPress={onRescan}
          />
          <Button
            label={t("review.confirm")}
            style={{ flex: 1 }}
            disabled={busy}
            onPress={() => {
              // The room is in: the one success pattern of the scan.
              void playHaptic("roomVerified");
              onConfirm();
            }}
          />
        </View>
      </Animated.View>
    </View>
  );
}
