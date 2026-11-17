// The scan's one line of guidance, over the camera. A new line fades in
// over the old one with the ease preset; with reduced motion it just changes.
import { GlassSurface, motion, Text, useTheme } from "@sajao/ui";
import Animated, { Easing, FadeIn, FadeOut } from "react-native-reanimated";

export function ScanInstruction({ id, text }: { id: string; text: string }) {
  const { tokens, duration } = useTheme();
  const { spacing, radius } = tokens;
  const fade = duration(motion.ease.durationMs);
  const easing = Easing.bezier(...motion.ease.bezier);
  return (
    <Animated.View
      key={id}
      entering={fade > 0 ? FadeIn.duration(fade).easing(easing) : undefined}
      exiting={fade > 0 ? FadeOut.duration(fade / 2).easing(easing) : undefined}
      style={{ alignItems: "center" }}
    >
      <GlassSurface
        tone="dark"
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
        testID="scan-instruction"
        style={{
          paddingHorizontal: spacing.gutter,
          paddingVertical: spacing.lg,
          borderRadius: radius.pill,
        }}
      >
        <Text variant="bodyStrong" tone="onDark" style={{ textAlign: "center" }}>
          {text}
        </Text>
      </GlassSurface>
    </Animated.View>
  );
}
