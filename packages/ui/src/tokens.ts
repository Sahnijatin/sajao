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
  /** Light glass: white at 62% over a live blur. Used over the canvas and photos. */
  light: {
    fill: "rgba(255, 255, 255, 0.62)",
    border: "rgba(255, 255, 255, 0.7)",
    saturation: 1.8,
    /** Low tier: no live blur, so the tint carries the surface on its own. */
    fallbackFill: "rgba(255, 255, 255, 0.9)",
    text: "#1d1d1f",
  },
  /** Dark glass: for camera screens, where the picture behind is busy and bright. */
  dark: {
    fill: "rgba(20, 22, 26, 0.42)",
    border: "rgba(255, 255, 255, 0.18)",
    saturation: 1.6,
    fallbackFill: "rgba(20, 22, 26, 0.78)",
    text: "#ffffff",
  },
  /** Blur radius in px, both tones. */
  blurRadius: 28,
} as const;

export type GlassTone = "light" | "dark";

export const radius = {
  pane: 20,
  card: 20,
  /** Top corners of bottom sheets. */
  sheet: 30,
  /** Buttons and chips are fully rounded. */
  pill: 999,
} as const;

// The spacing ladder used on the approved mockups.
export const spacing = {
  /** Between stacked lines of text. */
  xxs: 2,
  xs: 4,
  /** Icon to its label. */
  sm: 6,
  /** Between chips and between tiles. */
  md: 8,
  /** Between buttons in a row. */
  lg: 10,
  /** Inside list rows and between a thumbnail and its text. */
  xl: 12,
  /** Between sections inside a sheet. */
  xxl: 14,
  /** Screen side padding and card padding. */
  gutter: 16,
  /** Bottom padding of sheets, above the home indicator. */
  sheetBottom: 26,
} as const;

/** Control heights on the mockups. */
export const controlHeight = {
  /** Primary pill buttons. */
  button: 56,
  /** Small pills such as "Change" and "Buy". */
  buttonSmall: 32,
  chip: 36,
} as const;

/** Minimum touch target: 48dp on Android, 44pt on iOS. */
export const touchTarget = Platform.OS === "android" ? 48 : 44;

// Three stacked soft shadows on standard devices; one on the low tier.
export const shadows = {
  standard: {
    card: "0 1px 2px rgba(29, 29, 31, 0.04), 0 4px 12px rgba(29, 29, 31, 0.06), 0 16px 32px rgba(29, 29, 31, 0.08)",
    /** Upward shadow where a sheet meets the content behind it. */
    sheet: "0 -16px 40px rgba(29, 29, 31, 0.12)",
    /** Glow under the accent call to action. */
    accentGlow: "0 10px 24px rgba(10, 124, 255, 0.35)",
    /** The selected segment in a segmented control. */
    segment: "0 2px 8px rgba(29, 29, 31, 0.10)",
  },
  low: {
    card: "0 2px 8px rgba(29, 29, 31, 0.08)",
    sheet: "0 -4px 16px rgba(29, 29, 31, 0.10)",
    accentGlow: "none",
    segment: "0 1px 3px rgba(29, 29, 31, 0.10)",
  },
} as const;

export type FontWeight = "regular" | "medium" | "semibold";
export type FontFace = FontWeight | "serif" | "serifItalic";

// Headlines are Instrument Serif, bundled on both platforms. Body text is
// SF Pro (the system font) on iOS and bundled Geist on Android. The app loads
// the bundled files at startup under exactly these family names.
export const fontFamilies = {
  serif: "InstrumentSerif-Regular",
  serifItalic: "InstrumentSerif-Italic",
  regular: "Geist-Regular",
  medium: "Geist-Medium",
  semibold: "Geist-SemiBold",
} as const satisfies Record<FontFace, string>;

const iosWeights: Record<FontWeight, "400" | "500" | "600"> = {
  regular: "400",
  medium: "500",
  semibold: "600",
};

export function fontFor(face: FontFace, os: string = Platform.OS) {
  if (face === "serif" || face === "serifItalic" || os === "android") {
    return { fontFamily: fontFamilies[face] };
  }
  return { fontWeight: iosWeights[face] };
}

interface TypeStyle {
  fontSize: number;
  lineHeight: number;
  face: FontFace;
  letterSpacing?: number;
}

// Sizes taken from the approved mockups.
export const typography = {
  /** The one large headline on a screen, such as the home hero. */
  display: { fontSize: 46, lineHeight: 46, face: "serif", letterSpacing: -0.8 },
  /** Screen and sheet headlines. */
  title: { fontSize: 34, lineHeight: 36, face: "serif" },
  /** Section headlines. */
  heading: { fontSize: 26, lineHeight: 28, face: "serif" },
  /** Totals and other large numbers. */
  figure: { fontSize: 24, lineHeight: 28, face: "semibold", letterSpacing: -0.4 },
  /** Button labels and item names. */
  bodyStrong: { fontSize: 16, lineHeight: 22, face: "semibold" },
  body: { fontSize: 16, lineHeight: 23, face: "regular" },
  bodySmall: { fontSize: 14, lineHeight: 20, face: "regular" },
  label: { fontSize: 14, lineHeight: 18, face: "semibold" },
  /** Secondary lines and segmented controls. */
  meta: { fontSize: 13, lineHeight: 18, face: "medium" },
  caption: { fontSize: 12, lineHeight: 16, face: "regular" },
  /** Chips, badges and pills. */
  captionStrong: { fontSize: 12, lineHeight: 16, face: "semibold" },
  /** Legal lines and labels on the plan. */
  micro: { fontSize: 11, lineHeight: 14, face: "regular" },
} as const satisfies Record<string, TypeStyle>;

export type TypographyVariant = keyof typeof typography;

export const lightTokens = {
  colors,
  glass,
  radius,
  spacing,
  controlHeight,
  shadows,
  typography,
} as const;

export type Tokens = typeof lightTokens;

// Dark theme is reserved: it becomes a second entry here with the LiveMap
// dark values. Camera screens always use glass on camera, in either scheme.
export const themes = { light: lightTokens } as const;
export type ColorScheme = keyof typeof themes;
