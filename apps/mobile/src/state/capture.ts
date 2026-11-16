// The last finished scan on this phone and the state of its upload. In
// memory: the files themselves are on disk in the capture's folder.
import { create } from "zustand";
import type { LocalCapture } from "@/capture/package/native-capture";

export interface UploadStatus {
  /**
   * idle: nothing to upload. waiting: this build has no server to upload to
   * yet, the scan stays on the phone. failed: call the upload again to resume.
   */
  state: "idle" | "waiting" | "uploading" | "done" | "failed";
  /** Files finished and files in total, while uploading. */
  finished: number;
  total: number;
  error?: string;
}

interface CaptureStore {
  last: LocalCapture | null;
  upload: UploadStatus;
  setLast(capture: LocalCapture | null): void;
  setUpload(upload: UploadStatus): void;
}

export const useCaptureStore = create<CaptureStore>((set) => ({
  last: null,
  upload: { state: "idle", finished: 0, total: 0 },
  setLast: (last) => set({ last }),
  setUpload: (upload) => set({ upload }),
}));
