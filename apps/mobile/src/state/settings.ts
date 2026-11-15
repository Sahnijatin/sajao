// On-device settings. Guest-first: these work with no account.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Language } from "@/i18n";
import type { LengthUnits } from "@/utils/format-length";

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
      units: "cm",
      setLanguage: (language) => set({ language }),
      setUnits: (units) => set({ units }),
    }),
    {
      name: "sajao.settings",
      version: 1,
      storage: createJSONStorage(() => AsyncStorage),
      partialize: ({ language, units }) => ({ language, units }),
    },
  ),
);
