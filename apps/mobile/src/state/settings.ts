// On-device settings. Guest-first: these work with no account.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Language } from "@/i18n";
import type { LengthUnits } from "@/utils/format-length";

/** Rooms are talked about in feet and inches in India; centimetres are the alternative. */
export const DEFAULT_UNITS: LengthUnits = "ft_in";

type Saved = Pick<SettingsState, "language" | "units">;

/**
 * Version 1 saved centimetres for everyone, chosen or not, because that was
 * the default. Those move to the new default; a saved choice of feet and
 * inches is kept. From version 2 on, what is saved is kept as it is.
 */
export function migrateSettings(saved: unknown, version: number): Saved {
  const state = (saved ?? {}) as Partial<Saved>;
  const units = state.units === "cm" || state.units === "ft_in" ? state.units : DEFAULT_UNITS;
  return {
    language: state.language ?? null,
    units: version < 2 && units === "cm" ? DEFAULT_UNITS : units,
  };
}

interface SettingsState {
  /** null follows the device language. */
  language: Language | null;
  units: LengthUnits;
  setLanguage: (language: Language) => void;
  setUnits: (units: LengthUnits) => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      language: null,
      units: DEFAULT_UNITS,
      setLanguage: (language) => set({ language }),
      setUnits: (units) => set({ units }),
    }),
    {
      name: "sajao.settings",
      version: 2,
      migrate: migrateSettings,
      storage: createJSONStorage(() => AsyncStorage),
      partialize: ({ language, units }) => ({ language, units }),
    },
  ),
);
