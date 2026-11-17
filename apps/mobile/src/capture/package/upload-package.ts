// Uploads a scan's capture package. Each file goes up with the resumable
// uploader; its storage key is remembered under a stable name, so running
// this again after a crash or a lost connection skips what already
// arrived and resumes the rest. Same inputs, same package: idempotent.
import type { CapturePackage } from "@sajao/schemas";
import { FileTooLargeError } from "@/uploads/resumable-upload";
import { buildPackage, type PackageFiles, type RecorderState } from "./recorder";

export type PackageFileKind =
  "keyframe" | "video" | "planes" | "scene_mesh" | "depth" | "sensor_log";

export interface PackageUploadDeps {
  /** Upload one local file, resuming if it was started before. Resolves with its storage key. */
  uploadFile(file: {
    localId: string;
    uri: string;
    kind: PackageFileKind;
  }): Promise<{ key: string }>;
  /** Write the sensor log to a local file and return its uri. */
  writeText(name: string, text: string): Promise<string>;
  /** Remembers finished uploads across app restarts. */
  done: {
    get(localId: string): Promise<string | null>;
    set(localId: string, key: string): Promise<void>;
  };
  onProgress?: (finished: number, total: number) => void;
  /** The video was over the server's size limit and was left out; the rest of the package went up. */
  onVideoSkipped?: () => void;
  /** Files sent at the same time. Default 6. */
  concurrency?: number;
}

export async function uploadCapturePackage(
  captureId: string,
  state: RecorderState,
  files: PackageFiles,
  deps: PackageUploadDeps,
): Promise<CapturePackage> {
  const sensorUri = await deps.writeText(`${captureId}-sensors.jsonl`, state.sensorLog.join("\n"));
  // Small files first, the video last: the twin can start from keyframes.
  const queue: { name: string; uri: string; kind: PackageFileKind }[] = [
    { name: "sensor_log", uri: sensorUri, kind: "sensor_log" },
    ...files.keyframes.map((frame) => ({
      name: `keyframe-${frame.id}`,
      uri: frame.uri,
      kind: "keyframe" as const,
    })),
    ...(files.planes ? [{ name: "planes", uri: files.planes, kind: "planes" as const }] : []),
    ...(files.sceneMesh
      ? [{ name: "scene_mesh", uri: files.sceneMesh, kind: "scene_mesh" as const }]
      : []),
    ...(files.depth ? [{ name: "depth", uri: files.depth, kind: "depth" as const }] : []),
    ...(files.video ? [{ name: "video", uri: files.video, kind: "video" as const }] : []),
  ];

  const keys: Record<string, string> = {};
  let finished = 0;
  const sendOne = async (item: (typeof queue)[number]) => {
    const localId = `${captureId}/${item.name}`;
    const known = await deps.done.get(localId);
    let key = known;
    if (!key) {
      try {
        key = (await deps.uploadFile({ localId, uri: item.uri, kind: item.kind })).key;
      } catch (error) {
        // The twin is built from keyframes and poses; a video over the
        // server's limit must not hold the whole scan back.
        if (item.kind !== "video" || !(error instanceof FileTooLargeError)) throw error;
        deps.onVideoSkipped?.();
        finished += 1;
        deps.onProgress?.(finished, queue.length);
        return;
      }
      await deps.done.set(localId, key);
    }
    keys[item.name] = key;
    finished += 1;
    deps.onProgress?.(finished, queue.length);
  };
  // Several files at once: the scan is up sooner, and when the app goes to
  // the background the files already handed to the phone keep going.
  let next = 0;
  let failure: unknown;
  const worker = async () => {
    while (failure === undefined && next < queue.length) {
      const item = queue[next];
      next += 1;
      if (!item) return;
      try {
        await sendOne(item);
      } catch (error) {
        failure ??= error;
      }
    }
  };
  const lanes = Math.max(1, Math.min(deps.concurrency ?? 6, queue.length));
  await Promise.all(Array.from({ length: lanes }, worker));
  // Files in flight were allowed to finish, so nothing sent is thrown away.
  if (failure !== undefined) throw failure;

  const sensorLog = keys.sensor_log;
  if (!sensorLog) throw new Error("Sensor log was not uploaded");
  return buildPackage(state, {
    keyframes: Object.fromEntries(
      files.keyframes.map((frame) => [frame.id, keys[`keyframe-${frame.id}`] ?? ""]),
    ),
    sensorLog,
    ...(keys.video ? { video: keys.video } : {}),
    ...(keys.planes ? { planes: keys.planes } : {}),
    ...(keys.scene_mesh ? { sceneMesh: keys.scene_mesh } : {}),
    ...(keys.depth ? { depth: keys.depth } : {}),
  });
}
