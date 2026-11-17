// The last finished scan on this phone and the state of its upload. In
// memory: the files themselves are on disk in the capture's folder.
import { create } from "zustand";
import type { MeterMissing } from "@/capture/coverage-meter";
import type { LocalCapture } from "@/capture/package/native-capture";
import type { RoomJob } from "@/rooms/room-job";

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
  /** Bytes sent for this scan, once it is uploaded. */
  bytes?: number;
}

interface CaptureStore {
  last: LocalCapture | null;
  /**
   * What the coverage meter still wanted when the last scan ended: empty
   * lists and zeros when the scan was complete, the missing parts after
   * "Finish anyway". Null when the meter did not run. For the review to name.
   */
  missing: MeterMissing | null;
  setMissing(missing: MeterMissing | null): void;
  /** The phone the last scan was made on, for a retry of its upload. */
  device: { platform: "ios" | "android"; tier: "standard" | "low"; has_ar: boolean } | null;
  setDevice(device: CaptureStore["device"]): void;
  upload: UploadStatus;
  /** The room made from the last scan and its job at the server; null until the scan is up. */
  room: RoomJob | null;
  setRoom(room: RoomJob | null): void;
  setLast(capture: LocalCapture | null): void;
  setUpload(upload: UploadStatus): void;
}

export const useCaptureStore = create<CaptureStore>((set) => ({
  last: null,
  missing: null,
  setMissing: (missing) => set({ missing }),
  device: null,
  setDevice: (device) => set({ device }),
  upload: { state: "idle", finished: 0, total: 0 },
  room: null,
  setRoom: (room) => set({ room }),
  setLast: (last) => set({ last }),
  setUpload: (upload) => set({ upload }),
}));
