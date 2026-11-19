// Consent at first use, kept on this phone. Asked again when the wording it
// was given for changes (a new version), and after the account is deleted.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

/** Raise this when what the person agrees to changes, so they are asked again. */
export const CONSENT_VERSION = "1";

interface ConsentStore {
  acceptedVersion: string | null;
  acceptedAtMs: number | null;
  accept(atMs?: number): void;
}

export const useConsent = create<ConsentStore>()(
  persist(
    (set) => ({
      acceptedVersion: null,
      acceptedAtMs: null,
      accept: (atMs = Date.now()) => set({ acceptedVersion: CONSENT_VERSION, acceptedAtMs: atMs }),
    }),
    {
      name: "sajao.consent",
      version: 1,
      storage: createJSONStorage(() => AsyncStorage),
      partialize: ({ acceptedVersion, acceptedAtMs }) => ({ acceptedVersion, acceptedAtMs }),
    },
  ),
);

/** Whether the person has agreed to the current wording. */
export function hasConsent(state: { acceptedVersion: string | null }): boolean {
  return state.acceptedVersion === CONSENT_VERSION;
}

/** False until the saved answer has been read, so the consent screen never flashes. */
export function useConsentLoaded(): boolean {
  return useSyncExternalStore(
    (onChange) => useConsent.persist.onFinishHydration(onChange),
    () => useConsent.persist.hasHydrated(),
    () => useConsent.persist.hasHydrated(),
  );
}
