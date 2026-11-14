// LiveMap design tokens, from docs/10-design-language-and-motion.md.
// The room is the hero, so the interface stays neutral: one accent, soft
// shadows, frosted glass. Every screen reads its values from here.
import { Platform } from "react-native";

export const colors = {
  canvas: "#eef0f5",
  surface: "#ffffff",
  ink: "#1d1d1f",
  inkSecondary: "#55595f",
  inkTertiary: "#636873",
  accent: "#0a7cff",
  accentTint: "rgba(10, 124, 255, 0.10)",
  onAccent: "#ffffff",
  success: "#1fae55",
  danger: "#ff3b30",
  warning: "#ff8a00",
  hairline: "rgba(29, 29, 31, 0.08)",
} as const;

export const glass = {
  /** White at 62% over a live blur. */
  fill: "rgba(255, 255, 255, 0.62)",
  /** Blur radius in px; saturation 180% where the platform supports it. */
  blurRadius: 28,
  saturation: 1.8,
  border: "rgba(255, 255, 255, 0.7)",
  /** Low tier: no live blur, so the tint carries the surface on its own. */
  fallbackFill: "rgba(255, 255, 255, 0.9)",
} as const;

export const radius = {
  pane: 20,
  card: 14,
  pill: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

/** Minimum touch target: 48dp on Android, 44pt on iOS. */
export const touchTarget = Platform.OS === "android" ? 48 : 44;

// Three stacked soft shadows on standard devices; one on the low tier.
export const shadows = {
  standard:
    "0 1px 2px rgba(29, 29, 31, 0.04), 0 4px 12px rgba(29, 29, 31, 0.06), 0 16px 32px rgba(29, 29, 31, 0.08)",
  low: "0 2px 8px rgba(29, 29, 31, 0.08)",
} as const;

export type FontWeight = "regular" | "medium" | "semibold";

// SF Pro is the system font on iOS. Geist is bundled on Android, one file
// per weight, loaded by the app at startup.
const androidFamilies: Record<FontWeight, string> = {
  regular: "Geist-Regular",
  medium: "Geist-Medium",
  semibold: "Geist-SemiBold",
};
const iosWeights: Record<FontWeight, "400" | "500" | "600"> = {
  regular: "400",
  medium: "500",
  semibold: "600",
};

export function fontFor(weight: FontWeight, os: string = Platform.OS) {
  return os === "android"
    ? { fontFamily: androidFamilies[weight] }
    : { fontWeight: iosWeights[weight] };
}

export const typography = {
  title: { fontSize: 28, lineHeight: 34, weight: "semibold" },
  heading: { fontSize: 20, lineHeight: 26, weight: "semibold" },
  body: { fontSize: 16, lineHeight: 22, weight: "regular" },
  label: { fontSize: 14, lineHeight: 18, weight: "medium" },
  caption: { fontSize: 12, lineHeight: 16, weight: "regular" },
} as const satisfies Record<string, { fontSize: number; lineHeight: number; weight: FontWeight }>;

export type TypographyVariant = keyof typeof typography;

export const lightTokens = { colors, glass, radius, spacing, shadows, typography } as const;

export type Tokens = typeof lightTokens;

// Dark theme is reserved: it becomes a second entry here with the LiveMap
// dark values. Camera screens always use glass on camera, in either scheme.
export const themes = { light: lightTokens } as const;
export type ColorScheme = keyof typeof themes;
