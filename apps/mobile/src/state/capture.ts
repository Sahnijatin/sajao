// The last finished scan on this phone, waiting for upload. In memory: the
// files themselves are on disk in the capture's folder.
import { create } from "zustand";
import type { LocalCapture } from "@/capture/package/native-capture";

interface CaptureStore {
  last: LocalCapture | null;
  setLast(capture: LocalCapture | null): void;
}

export const useCaptureStore = create<CaptureStore>((set) => ({
  last: null,
  setLast: (last) => set({ last }),
}));
