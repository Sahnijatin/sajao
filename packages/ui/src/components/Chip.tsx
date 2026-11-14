import { useEffect } from "react";
import { Pressable, type PressableProps } from "react-native";
import Animated, {
  interpolateColor,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";
import { type HapticMoment, playHaptic } from "../haptics";
import { motion } from "../motion";
import { useTheme } from "../theme";
import { touchTarget } from "../tokens";
import { Text } from "./Text";

export interface ChipProps extends Omit<PressableProps, "children" | "style"> {
  label: string;
  selected: boolean;
  haptic?: HapticMoment;
}

const VISUAL_HEIGHT = 36;

export function Chip({ label, selected, haptic, onPress, ...rest }: ChipProps) {
  const { tokens, reducedMotion } = useTheme();
  const { colors, radius, spacing } = tokens;
  const progress = useSharedValue(selected ? 1 : 0);

  useEffect(() => {
    const target = selected ? 1 : 0;
    // Reduced motion: an instant change. Otherwise the selection spring.
    progress.set(reducedMotion ? target : withSpring(target, motion.selectionSpring));
  }, [selected, reducedMotion, progress]);

  const animatedStyle = useAnimatedStyle(() => ({
    backgroundColor: interpolateColor(progress.get(), [0, 1], [colors.surface, colors.accentTint]),
    borderColor: interpolateColor(progress.get(), [0, 1], [colors.hairline, colors.accent]),
  }));

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      // The visual is smaller than the touch target, so widen the hit area.
      hitSlop={(touchTarget - VISUAL_HEIGHT) / 2}
      onPress={(event) => {
        if (haptic) void playHaptic(haptic);
        onPress?.(event);
      }}
      {...rest}
    >
      <Animated.View
        style={[
          {
            height: VISUAL_HEIGHT,
            paddingHorizontal: spacing.lg,
            borderRadius: radius.pill,
            borderWidth: 1,
            justifyContent: "center",
          },
          animatedStyle,
        ]}
      >
        <Text variant="label" tone={selected ? "accent" : "secondary"}>
          {label}
        </Text>
      </Animated.View>
    </Pressable>
  );
}
