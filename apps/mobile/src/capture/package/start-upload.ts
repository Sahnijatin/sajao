// Starts the upload of a finished scan and tracks it in the capture store.
// Without a server configured for this build (no API URL yet) the scan stays
// on the phone and is marked as waiting; nothing is lost.
import { createApiClient } from "@sajao/api-client";
import { configResult } from "@/config";
import { type UploadStatus, useCaptureStore } from "@/state/capture";
import { putPart, uploadsApi } from "@/uploads/api";
import { uploadResumable } from "@/uploads/resumable-upload";
import { finishedUploads, mediaIdFor, uploadStateStore } from "@/uploads/stores";
import type { LocalCapture } from "./native-capture";
import { type CaptureDeviceInfo, uploadAndRegister, uploadSpec, uuidV4 } from "./upload-capture";

const setStatus = (upload: UploadStatus) => useCaptureStore.getState().setUpload(upload);

/** Upload and register a scan. Never throws: the outcome is in the capture store. Safe to call again. */
export async function startCaptureUpload(
  local: LocalCapture,
  device: CaptureDeviceInfo,
): Promise<void> {
  useCaptureStore.getState().setDevice(device);
  let videoSkipped = false;
  // What this scan really cost to upload, shown once it is up.
  let bytes = 0;
  const config = configResult.ok ? configResult.config : null;
  if (!config?.apiUrl || !config.supabase) {
    setStatus({ state: "waiting", finished: 0, total: 0 });
    return;
  }
  const supabase = config.supabase;
  try {
    setStatus({ state: "uploading", finished: 0, total: 0 });
    // Loaded only when there is a server to upload to, so the scan screen
    // itself never depends on the auth or file libraries.
    const { guestAccessToken } = await import("@/auth/guest-session");
    const { fileSource, writeCacheText } = await import("@/uploads/file-source");
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
  } catch (error) {
    setStatus({
      state: "failed",
      finished: 0,
      total: 0,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
