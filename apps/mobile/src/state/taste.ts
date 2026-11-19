// The taste and budget given in onboarding, saved on this phone. Asked once,
// before the first room's designs, and changeable from Profile. The server
// builds the TasteProfile and the Brief from these answers when its
// endpoints exist; until then they wait here.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { TasteAnswers } from "@/taste/taste-session";

interface TasteStore {
  answers: TasteAnswers | null;
  /** The budget given for the last room, to start the next room's from. */
  lastBudget: TasteAnswers["budget"] | null;
  setAnswers(answers: TasteAnswers): void;
  setLastBudget(budget: TasteAnswers["budget"]): void;
}

export const useTaste = create<TasteStore>()(
  persist(
    (set) => ({
      answers: null,
      lastBudget: null,
      setAnswers: (answers) => set({ answers }),
      setLastBudget: (lastBudget) => set({ lastBudget }),
    }),
    {
      name: "sajao.taste",
      version: 1,
      storage: createJSONStorage(() => AsyncStorage),
      partialize: ({ answers, lastBudget }) => ({ answers, lastBudget }),
    },
  ),
);
