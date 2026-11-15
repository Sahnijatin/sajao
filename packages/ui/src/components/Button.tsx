import { useState } from "react";
import { Pressable, type PressableProps, type StyleProp, type ViewStyle } from "react-native";
import Animated, { cubicBezier } from "react-native-reanimated";
import { type HapticMoment, playHaptic } from "../haptics";
import { motion } from "../motion";
import { useTheme } from "../theme";
import { touchTarget } from "../tokens";
import { Text } from "./Text";

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);
const pressEasing = cubicBezier(...motion.press.bezier);

export interface ButtonProps extends Omit<PressableProps, "children" | "style"> {
  label: string;
  variant?: "primary" | "secondary" | "ghost";
  /** Play a haptic from the map on press, for presses that are real milestones. */
  haptic?: HapticMoment;
  style?: StyleProp<ViewStyle>;
}

export function Button({
  label,
  variant = "primary",
  haptic,
  disabled,
  onPressIn,
  onPressOut,
  onPress,
  style,
  ...rest
}: ButtonProps) {
  const { tokens, duration } = useTheme();
  const [pressed, setPressed] = useState(false);
  const { colors, radius, spacing } = tokens;

  const background = {
    primary: colors.accent,
    secondary: colors.accentTint,
    ghost: "transparent",
  }[variant];

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      pressRetentionOffset={16}
      // Feedback on press-in, commit on press-out.
      onPressIn={(event) => {
        setPressed(true);
        onPressIn?.(event);
      }}
      onPressOut={(event) => {
        setPressed(false);
        onPressOut?.(event);
      }}
      onPress={(event) => {
        if (haptic) void playHaptic(haptic);
        onPress?.(event);
      }}
      style={[
        {
          minHeight: touchTarget,
          paddingHorizontal: spacing.xl,
          borderRadius: radius.card,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: background,
          opacity: disabled ? 0.4 : 1,
          transform: [{ scale: pressed ? motion.press.scale : 1 }],
          transitionProperty: "transform",
          transitionDuration: duration(motion.press.durationMs),
          transitionTimingFunction: pressEasing,
        },
        style,
      ]}
      {...rest}
    >
      <Text variant="label" tone={variant === "primary" ? "onAccent" : "accent"}>
        {label}
      </Text>
    </AnimatedPressable>
  );
}
