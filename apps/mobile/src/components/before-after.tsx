// One before and after, for the empty My home. The after slowly crossfades
// over the before and back: the promise of the app in one picture. With
// reduced motion the two sit side by side and nothing moves.
import { GlassSurface, motion, Text, useTheme } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { type StyleProp, StyleSheet, View, type ViewStyle } from "react-native";
import Animated, { cubicBezier } from "react-native-reanimated";
import type { RoomStill } from "@/rooms/rooms";
import { RoomStillView } from "@/rooms/room-still";

export interface BeforeAfterProps {
  before: RoomStill;
  after: RoomStill;
  style?: StyleProp<ViewStyle>;
}

/** One full loop: hold the before, fade to the after, hold, fade back. */
export const BEFORE_AFTER_LOOP_MS = 7000;

const crossfade = {
  "0%": { opacity: 0 },
  "30%": { opacity: 0 },
  "50%": { opacity: 1 },
  "80%": { opacity: 1 },
  "100%": { opacity: 0 },
};
const easing = cubicBezier(...motion.ease.bezier);

function Tag({ text }: { text: string }) {
  const { tokens } = useTheme();
  return (
    <GlassSurface
      style={{
        position: "absolute",
        left: tokens.spacing.xl,
        bottom: tokens.spacing.xl,
        paddingHorizontal: tokens.spacing.xl,
        paddingVertical: tokens.spacing.xs,
        borderRadius: tokens.radius.pill,
      }}
    >
      <Text variant="captionStrong">{text}</Text>
    </GlassSurface>
  );
}

export function BeforeAfter({ before, after, style }: BeforeAfterProps) {
  const { t } = useTranslation();
  const { tokens, tier, reducedMotion } = useTheme();
  const frame = {
    borderRadius: tokens.radius.card,
    borderCurve: "continuous",
    overflow: "hidden",
    boxShadow: tokens.shadows[tier].card,
  } as const;

  if (reducedMotion) {
    return (
      <View
        testID="before-after"
        accessible
        accessibilityRole="image"
        accessibilityLabel={t("home.empty.picture")}
        style={[frame, { flexDirection: "row", gap: tokens.spacing.xxs }, style]}
      >
        <View style={{ flex: 1 }}>
          <RoomStillView still={before} style={{ flex: 1 }} />
          <Tag text={t("home.empty.before")} />
        </View>
        <View style={{ flex: 1 }}>
          <RoomStillView still={after} style={{ flex: 1 }} />
          <Tag text={t("home.empty.after")} />
        </View>
      </View>
    );
  }

  return (
    <View
      testID="before-after"
      accessible
      accessibilityRole="image"
      accessibilityLabel={t("home.empty.picture")}
      style={[frame, style]}
    >
      <RoomStillView still={before} style={StyleSheet.absoluteFill} />
      <Tag text={t("home.empty.before")} />
      <Animated.View
        style={[
          StyleSheet.absoluteFill,
          {
            animationName: crossfade,
            // The low tier keeps the same slow loop: a faster one would read as a flicker.
            animationDuration: BEFORE_AFTER_LOOP_MS,
            animationIterationCount: "infinite",
            animationTimingFunction: easing,
          },
        ]}
      >
        <RoomStillView still={after} style={StyleSheet.absoluteFill} />
        <Tag text={t("home.empty.after")} />
      </Animated.View>
    </View>
  );
}
