import { createContext, type ReactNode, useContext, useMemo, useState } from "react";
import { useReducedMotion } from "react-native-reanimated";
import { detectDeviceTier, type DeviceTier } from "./deviceTier";
import { resolveDuration } from "./motion";
import { type ColorScheme, themes, type Tokens } from "./tokens";

export interface Theme {
  scheme: ColorScheme;
  tokens: Tokens;
  tier: DeviceTier;
  reducedMotion: boolean;
  /** Duration to run for a preset duration, after reduced motion and tier. */
  duration: (durationMs: number) => number;
}

const ThemeContext = createContext<Theme | null>(null);

export interface ThemeProviderProps {
  children: ReactNode;
  /** Override the detected tier, for the gallery and tests. */
  tier?: DeviceTier;
  /** Override the system reduced-motion setting, for the gallery and tests. */
  reducedMotion?: boolean;
}

export function ThemeProvider({ children, tier, reducedMotion }: ThemeProviderProps) {
  const [detectedTier] = useState(detectDeviceTier);
  const systemReducedMotion = useReducedMotion();
  const resolvedTier = tier ?? detectedTier;
  const resolvedReducedMotion = reducedMotion ?? systemReducedMotion;

  const theme = useMemo<Theme>(() => {
    const context = { tier: resolvedTier, reducedMotion: resolvedReducedMotion };
    return {
      scheme: "light",
      tokens: themes.light,
      ...context,
      duration: (durationMs) => resolveDuration(durationMs, context),
    };
  }, [resolvedTier, resolvedReducedMotion]);

  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error("useTheme must be used inside ThemeProvider");
  return theme;
}
