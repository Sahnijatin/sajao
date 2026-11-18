// Resumable upload of one file, straight to object storage through signed
// URLs. The file goes up in parts. If the connection drops, the next call
// asks the API which parts arrived and sends only the rest.
//
// Everything that touches the network or the disk is passed in, so this
// logic is tested without a phone.

export type MediaKind = "photo" | "video" | "data";

export interface UploadedPart {
  part_number: number;
  size_bytes: number;
  etag: string;
}

export interface UploadPlan {
  key: string;
  upload_id: string;
  part_size_bytes: number;
  part_count: number;
  uploaded: UploadedPart[];
  parts: { part_number: number; url: string }[];
}

/** The three API calls, see src/uploads/api.ts for the real ones. */
export interface UploadsApi {
  create(file: { kind: MediaKind; content_type: string; size_bytes: number }): Promise<UploadPlan>;
  /** Rejects with UploadGoneError when the upload no longer exists. */
  resume(ref: { key: string; upload_id: string; size_bytes: number }): Promise<UploadPlan>;
  complete(ref: {
    key: string;
    upload_id: string;
    parts: UploadedPart[];
  }): Promise<{ key: string; size_bytes: number }>;
}

export interface UploadSource {
  kind: MediaKind;
  contentType: string;
  sizeBytes: number;
  /** Bytes from start (inclusive) to end (exclusive). */
  slice(start: number, end: number): Promise<Blob | ArrayBuffer>;
  /** Where the file is on the phone, when it is a file. */
  uri?: string;
}

/** Where an unfinished upload is remembered across app restarts. */
export interface UploadStateStore {
  get(localId: string): Promise<{ key: string; upload_id: string } | null>;
  set(localId: string, state: { key: string; upload_id: string }): Promise<void>;
  remove(localId: string): Promise<void>;
}

/** Sends one part and returns its ETag. Rejects with PartUrlExpiredError on 403. */
export type PutPart = (url: string, body: Blob | ArrayBuffer) => Promise<string>;
/**
 * Sends a whole file as one part and returns its ETag. The phone's own
 * transfer service does the sending, so it carries on when the app is in
 * the background. Rejects with PartUrlExpiredError on 403.
 */
export type PutFile = (url: string, uri: string) => Promise<string>;

export class UploadGoneError extends Error {}
/** The server refused the file as too large; retrying will not help. */
export class FileTooLargeError extends Error {}
export class PartUrlExpiredError extends Error {}
/** The upload stopped but nothing is lost: call uploadResumable again to continue. */
export class UploadInterruptedError extends Error {}

export interface UploadOptions {
  /** A stable id for this file on this phone, so a later call can resume it. */
  localId: string;
  source: UploadSource;
  api: UploadsApi;
  putPart: PutPart;
  /** Used instead of putPart for a file that fits in one part. */
  putFile?: PutFile;
  store: UploadStateStore;
  onProgress?: (sentBytes: number, totalBytes: number) => void;
  maxAttemptsPerPart?: number;
  wait?: (ms: number) => Promise<void>;
}

const defaultWait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Backoff before retry n (1-based): 0.5 s, 1 s, 2 s, capped at 8 s. */
export function retryDelayMs(attempt: number): number {
  return Math.min(8000, 500 * 2 ** (attempt - 1));
}

async function startOrResume(options: UploadOptions): Promise<UploadPlan> {
  const { api, localId, source, store } = options;
  const saved = await store.get(localId);
  if (saved) {
    try {
      return await api.resume({ ...saved, size_bytes: source.sizeBytes });
    } catch (error) {
      if (!(error instanceof UploadGoneError)) throw error;
      // The stored upload expired or was already finished: start again.
      await store.remove(localId);
    }
  }
  const plan = await api.create({
    kind: source.kind,
    content_type: source.contentType,
    size_bytes: source.sizeBytes,
  });
  await store.set(localId, { key: plan.key, upload_id: plan.upload_id });
  return plan;
}

export async function uploadResumable(options: UploadOptions): Promise<{ key: string }> {
  const { api, localId, source, store, putPart, putFile, onProgress } = options;
  const maxAttempts = options.maxAttemptsPerPart ?? 4;
  const wait = options.wait ?? defaultWait;

  let plan = await startOrResume(options);
  const done = new Map(plan.uploaded.map((part) => [part.part_number, part]));
  const sent = () => [...done.values()].reduce((total, part) => total + part.size_bytes, 0);
  onProgress?.(sent(), source.sizeBytes);

  for (let number = 1; number <= plan.part_count; number += 1) {
    if (done.has(number)) continue;
    const start = (number - 1) * plan.part_size_bytes;
    const end = Math.min(source.sizeBytes, start + plan.part_size_bytes);

    for (let attempt = 1; ; attempt += 1) {
      const url = plan.parts.find((part) => part.part_number === number)?.url;
      try {
        if (!url) throw new PartUrlExpiredError();
        const whole = putFile && source.uri && plan.part_count === 1;
        const etag = whole
          ? await putFile(url, source.uri as string)
          : await putPart(url, await source.slice(start, end));
        done.set(number, { part_number: number, size_bytes: end - start, etag });
        onProgress?.(sent(), source.sizeBytes);
        break;
      } catch (error) {
        if (attempt >= maxAttempts) {
          // Keep the saved state: the parts already sent are not lost.
          throw new UploadInterruptedError(`Upload paused at part ${number}`, { cause: error });
        }
        if (error instanceof PartUrlExpiredError) {
          // Signed URLs are short-lived. Ask for fresh ones and carry on.
          plan = await api.resume({
            key: plan.key,
            upload_id: plan.upload_id,
            size_bytes: source.sizeBytes,
          });
        } else {
          await wait(retryDelayMs(attempt));
        }
      }
    }
  }

  const parts = [...done.values()].sort((a, b) => a.part_number - b.part_number);
  const completed = await api.complete({ key: plan.key, upload_id: plan.upload_id, parts });
  await store.remove(localId);
  return { key: completed.key };
}
