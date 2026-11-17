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
  /** The video was over the server's size limit and was left out. */
  videoSkipped?: boolean;
}

interface CaptureStore {
  last: LocalCapture | null;
  /** The phone the last scan was made on, for a retry of its upload. */
  device: { platform: "ios" | "android"; tier: "standard" | "low"; has_ar: boolean } | null;
  setDevice(device: CaptureStore["device"]): void;
  upload: UploadStatus;
  setLast(capture: LocalCapture | null): void;
  setUpload(upload: UploadStatus): void;
}

export const useCaptureStore = create<CaptureStore>((set) => ({
  last: null,
  device: null,
  setDevice: (device) => set({ device }),
  upload: { state: "idle", finished: 0, total: 0 },
  setLast: (last) => set({ last }),
  setUpload: (upload) => set({ upload }),
}));
