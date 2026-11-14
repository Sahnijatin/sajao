import { Text as NativeText, type TextProps as NativeTextProps } from "react-native";
import { useTheme } from "../theme";
import { fontFor, type TypographyVariant } from "../tokens";

export interface TextProps extends NativeTextProps {
  variant?: TypographyVariant;
  tone?: "primary" | "secondary" | "tertiary" | "accent" | "onAccent";
}

export function Text({ variant = "body", tone = "primary", style, ...rest }: TextProps) {
  const { tokens } = useTheme();
  const { fontSize, lineHeight, weight } = tokens.typography[variant];
  const color = {
    primary: tokens.colors.ink,
    secondary: tokens.colors.inkSecondary,
    tertiary: tokens.colors.inkTertiary,
    accent: tokens.colors.accent,
    onAccent: tokens.colors.onAccent,
  }[tone];
  return <NativeText style={[{ fontSize, lineHeight, color }, fontFor(weight), style]} {...rest} />;
}
