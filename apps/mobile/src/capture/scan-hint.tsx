// One capture hint at a time over the scan: a doorway, step back, or walk
// around a large object. Fades in with the ease preset (instant with reduced
// motion) and ticks once when a new hint appears.
import { GlassSurface, motion, playHaptic, resolveDuration, Text, useTheme } from "@sajao/ui";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import Animated, { Easing, FadeIn, FadeOut } from "react-native-reanimated";
import type { Hint } from "./ar/guidance";

export function ScanHint({ hint }: { hint: Hint }) {
  const { t } = useTranslation();
  const { tokens, tier, reducedMotion } = useTheme();
  const { spacing, radius } = tokens;
  const key = hint ? `${hint.id}${hint.id === "walkAround" ? `:${hint.kind}` : ""}` : null;
  const shown = useRef<string | null>(null);

  useEffect(() => {
    if (key && key !== shown.current) void playHaptic("levelReached");
    shown.current = key;
  }, [key]);

  if (!hint) return null;
  const duration = resolveDuration(motion.ease.durationMs, { reducedMotion, tier });
  const easing = Easing.bezier(...motion.ease.bezier);
  const text =
    hint.id === "walkAround"
      ? t("capture.hints.walkAround", { object: t(`capture.labels.${hint.kind}`).toLowerCase() })
      : t(`capture.hints.${hint.id}`);

  return (
    <Animated.View
      key={key}
      entering={FadeIn.duration(duration).easing(easing)}
      exiting={FadeOut.duration(duration).easing(easing)}
      style={{ alignItems: "center" }}
    >
      <GlassSurface
        tone="dark"
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
        testID="scan-hint"
        style={{
          paddingHorizontal: spacing.xxl,
          paddingVertical: spacing.md,
          borderRadius: radius.pill,
        }}
      >
        <Text variant="meta" tone="onDark">
          {text}
        </Text>
      </GlassSurface>
    </Animated.View>
  );
}
