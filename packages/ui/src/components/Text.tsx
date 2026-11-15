import { Text as NativeText, type TextProps as NativeTextProps } from "react-native";
import { useTheme } from "../theme";
import { fontFor, type TypographyVariant } from "../tokens";

export interface TextProps extends NativeTextProps {
  variant?: TypographyVariant;
  tone?: "primary" | "secondary" | "tertiary" | "accent" | "onAccent" | "onDark";
  /** Serif variants only: the italic cut, for one emphasised word in a headline. */
  italic?: boolean;
}

export function Text({ variant = "body", tone = "primary", italic, style, ...rest }: TextProps) {
  const { tokens } = useTheme();
  const type: { fontSize: number; lineHeight: number; face: string; letterSpacing?: number } =
    tokens.typography[variant];
  const color = {
    primary: tokens.colors.ink,
    secondary: tokens.colors.inkSecondary,
    tertiary: tokens.colors.inkTertiary,
    accent: tokens.colors.accent,
    onAccent: tokens.colors.onAccent,
    onDark: tokens.glass.dark.text,
  }[tone];
  const face = italic && type.face === "serif" ? "serifItalic" : tokens.typography[variant].face;
  return (
    <NativeText
      style={[
        { fontSize: type.fontSize, lineHeight: type.lineHeight, color },
        type.letterSpacing === undefined ? null : { letterSpacing: type.letterSpacing },
        fontFor(face),
        style,
      ]}
      {...rest}
    />
  );
}
