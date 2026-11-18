// Starts the upload of a finished scan and tracks it in the capture store.
// Without a server configured for this build (no API URL yet) the scan stays
// on the phone and is marked as waiting; nothing is lost.
//
// The scan is remembered until its upload is done, so an upload that stopped
// (the app was closed, the connection dropped) starts again by itself when
// the app next opens or comes back to the front. While it runs, the phone is
// asked to keep it going in the background.
import { createApiClient } from "@sajao/api-client";
import { configResult } from "@/config";
import { followRoom } from "@/rooms/room-job";
import { type UploadStatus, useCaptureStore } from "@/state/capture";
import { putPart, uploadsApi } from "@/uploads/api";
import { uploadResumable } from "@/uploads/resumable-upload";
import { finishedUploads, mediaIdFor, uploadStateStore } from "@/uploads/stores";
import type { LocalCapture } from "./native-capture";
import { clearPendingUpload, loadPendingUpload, savePendingUpload } from "./pending-upload";
import { type CaptureDeviceInfo, uploadAndRegister, uploadSpec, uuidV4 } from "./upload-capture";

const setStatus = (upload: UploadStatus) => useCaptureStore.getState().setUpload(upload);

let running: { captureId: string; done: Promise<void> } | null = null;

/** Upload and register a scan. Never throws: the outcome is in the capture store. Safe to call again. */
export function startCaptureUpload(local: LocalCapture, device: CaptureDeviceInfo): Promise<void> {
  // One upload at a time. A second call for the same scan joins the one that
  // runs; a new scan waits for the one before it.
  if (running?.captureId === local.captureId) return running.done;
  const before = running?.done ?? Promise.resolve();
  const mine = {
    captureId: local.captureId,
    done: before
      .then(() => upload(local, device))
      .finally(() => {
        if (running === mine) running = null;
      }),
  };
  running = mine;
  return mine.done;
}

/**
 * Carry on with an upload that did not finish. Called when the app opens and
 * when it comes back to the front; does nothing if there is none or one runs.
 */
export async function resumePendingUpload(): Promise<void> {
  if (running) return;
  const pending = await loadPendingUpload().catch(() => null);
  if (!pending || running) return;
  const store = useCaptureStore.getState();
  if (!store.last) store.setLast(pending.local);
  await startCaptureUpload(pending.local, pending.device);
}

async function upload(local: LocalCapture, device: CaptureDeviceInfo): Promise<void> {
  useCaptureStore.getState().setDevice(device);
  useCaptureStore.getState().setRoom(null);
  let videoSkipped = false;
  // What this scan really cost to upload, shown once it is up.
  let bytes = 0;
  const config = configResult.ok ? configResult.config : null;
  if (!config?.apiUrl || !config.supabase) {
    setStatus({ state: "waiting", finished: 0, total: 0 });
    return;
  }
  const supabase = config.supabase;
  // Remembered first, so even an upload that never got going is resumed.
  await savePendingUpload({ local, device }).catch(() => undefined);
  const background = await import("@/uploads/background").catch(() => null);
  try {
    setStatus({ state: "uploading", finished: 0, total: 0 });
    background?.keepUploading(true);
    // Loaded only when there is a server to upload to, so the scan screen
    // itself never depends on the auth or file libraries.
    const { guestAccessToken } = await import("@/auth/guest-session");
    const { fileSource, putFile, writeCacheText } = await import("@/uploads/file-source");
    const client = createApiClient({ baseUrl: config.apiUrl, newIdempotencyKey: uuidV4 });
    client.use({
      async onRequest({ request }) {
        request.headers.set("Authorization", `Bearer ${await guestAccessToken(supabase)}`);
        return request;
      },
    });
    const api = uploadsApi(client);
    await uploadAndRegister(local, device, {
      async uploadFile(file) {
        const spec = uploadSpec(file.kind);
        const source = fileSource(file.uri, spec.kind, spec.contentType);
        bytes += source.sizeBytes;
        return uploadResumable({
          localId: file.localId,
          source,
          api,
          putPart,
          putFile,
          store: uploadStateStore,
        });
      },
      writeText: async (name, text) => writeCacheText(name, text),
      done: finishedUploads,
      onProgress: (finished, total) => setStatus({ state: "uploading", finished, total }),
      onVideoSkipped: () => {
        videoSkipped = true;
      },
      async register(body) {
        const { response } = await client.POST("/v1/captures", {
          body,
          // The capture id makes a retry of this write the same request.
          headers: { "Idempotency-Key": `capture-${body.id}` },
        });
        if (!response.ok) throw new Error(`Registering the capture failed with ${response.status}`);
      },
      mediaId: (captureId) => mediaIdFor(captureId, uuidV4),
    });
    setStatus({
      state: "done",
      finished: 1,
      total: 1,
      bytes,
      ...(videoSkipped ? { videoSkipped } : {}),
    });
    await clearPendingUpload(local.captureId).catch(() => undefined);
    try {
      // The scan is up: make its room and follow the measuring. A failure
      // here loses nothing; the next upload call makes the same room again.
      await followRoom(
        {
          async create(captureId) {
            const { data } = await client.POST("/v1/rooms", {
              body: { capture_id: captureId },
              headers: { "Idempotency-Key": `room-${captureId}` },
            });
            if (!data) throw new Error("Could not create the room");
            return data;
          },
          async read(roomId) {
            const { data } = await client.GET("/v1/rooms/{room_id}", {
              params: { path: { room_id: roomId } },
            });
            if (!data) throw new Error("Could not read the room");
            return data;
          },
        },
        local.captureId,
        {
          onUpdate: (room) => useCaptureStore.getState().setRoom(room),
          sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
          now: Date.now,
        },
      );
    } catch {
      // The room line stays as it was; the upload itself is done.
    }
  } catch (error) {
    setStatus({
      state: "failed",
      finished: 0,
      total: 0,
      error: error instanceof Error ? error.message : String(error),
    });
  } finally {
    background?.keepUploading(false);
  }
}
