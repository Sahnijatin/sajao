// The last finished scan on this phone and the state of its upload. In
// memory: the files themselves are on disk in the capture's folder.
import { create } from "zustand";
import type { MeterMissing } from "@/capture/coverage-meter";
import type { LocalCapture } from "@/capture/package/native-capture";
import { breadcrumb } from "@/telemetry/breadcrumbs";

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
  /** The capture this status is for. */
  captureId?: string;
}

/** Where one capture's upload stands. "queued": waiting for the upload before it. */
export type UploadState = UploadStatus["state"] | "queued";

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
  /** The last capture's upload, as shown on My home. */
  upload: UploadStatus;
  /**
   * Each capture's upload state, by capture id. A room's job waits on its
   * own capture's upload here, never on whichever upload ran last.
   */
  uploads: Record<string, UploadState>;
  setLast(capture: LocalCapture | null): void;
  /** One capture's upload changed; My home shows it if it is the last capture's. */
  setUpload(upload: UploadStatus): void;
  /** A capture's upload is waiting for the one before it. */
  queueUpload(captureId: string): void;
}

export const useCaptureStore = create<CaptureStore>((set) => ({
  last: null,
  missing: null,
  setMissing: (missing) => set({ missing }),
  device: null,
  setDevice: (device) => set({ device }),
  upload: { state: "idle", finished: 0, total: 0 },
  uploads: {},
  setLast: (last) => set({ last }),
  setUpload: (upload) =>
    set((store) => {
      const id = upload.captureId;
      if (id && store.uploads[id] !== upload.state) {
        breadcrumb("upload", upload.state, {
          captureId: id,
          finished: upload.finished,
          total: upload.total,
          error: upload.error ?? null,
        });
      }
      const isLast = !id || !store.last || store.last.captureId === id;
      return {
        ...(isLast ? { upload } : {}),
        uploads: id ? { ...store.uploads, [id]: upload.state } : store.uploads,
      };
    }),
  queueUpload: (captureId) =>
    set((store) => {
      if (store.uploads[captureId]) return {};
      breadcrumb("upload", "queued", { captureId });
      return { uploads: { ...store.uploads, [captureId]: "queued" } };
    }),
}));
