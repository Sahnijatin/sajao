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
  /**
   * primary: the accent call to action. ink: the dark call to action used on
   * sheets. outline: the quieter choice beside one. tint and ghost: inline actions.
   */
  variant?: "primary" | "ink" | "outline" | "tint" | "ghost";
  /** large is the 56 px pill; small is the 32 px inline pill. */
  size?: "large" | "small";
  /** Play a haptic from the map on press, for presses that are real milestones. */
  haptic?: HapticMoment;
  style?: StyleProp<ViewStyle>;
}

export function Button({
  label,
  variant = "primary",
  size = "large",
  haptic,
  disabled,
  onPressIn,
  onPressOut,
  onPress,
  style,
  ...rest
}: ButtonProps) {
  const { tokens, tier, duration } = useTheme();
  const [pressed, setPressed] = useState(false);
  const { colors, radius, spacing, controlHeight } = tokens;
  const height = size === "large" ? controlHeight.button : controlHeight.buttonSmall;

  const background = {
    primary: colors.accent,
    ink: colors.ink,
    outline: colors.surface,
    tint: colors.accentTint,
    ghost: "transparent",
  }[variant];
  const labelTone = (
    {
      primary: "onAccent",
      ink: "onAccent",
      outline: "primary",
      tint: "accent",
      ghost: "accent",
    } as const
  )[variant];

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      pressRetentionOffset={16}
      // The small pill is shorter than a touch target, so widen the hit area.
      hitSlop={Math.max(0, (touchTarget - height) / 2)}
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
          height,
          paddingHorizontal: size === "large" ? spacing.gutter : spacing.xl,
          borderRadius: radius.pill,
          borderWidth: variant === "outline" ? 1 : 0,
          borderColor: colors.hairline,
          boxShadow:
            variant === "primary" && size === "large" ? tokens.shadows[tier].accentGlow : "none",
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
      <Text variant={size === "large" ? "bodyStrong" : "captionStrong"} tone={labelTone}>
        {label}
      </Text>
    </AnimatedPressable>
  );
}
