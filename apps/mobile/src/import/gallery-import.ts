// A capture made from photos or a video the person already has. It goes up
// in the same package format as a scan, with no AR data: no poses, planes or
// depth. The room that comes out of it is at the estimated confidence level,
// so nothing is claimed to fit until a measurement confirms it.
//
// A video is not uploaded. Frames are taken from it on the phone, evenly
// through its length, and those go up as the keyframes.
//
// Pure: what was picked in, a capture out. The picker and the frame grabber
// are in pick.ts.
import type { LocalCapture } from "@/capture/package/native-capture";
import { filesToUpload, startRecording } from "@/capture/package/recorder";

/** At most this many photos, and this many frames from a video. */
export const MAX_FRAMES = 20;
export const MIN_VIDEO_MS = 5_000;
export const MAX_VIDEO_MS = 120_000;

export interface PickedItem {
  uri: string;
  kind: "photo" | "video";
  widthPx: number;
  heightPx: number;
  /** Video only. */
  durationMs?: number;
}

export type ImportProblem =
  | "nothing"
  | "tooManyPhotos"
  | "photosAndVideo"
  | "severalVideos"
  | "videoTooShort"
  | "videoTooLong";

export type Selection =
  | { ok: true; photos: PickedItem[] }
  | { ok: true; video: PickedItem & { durationMs: number } }
  | { ok: false; problem: ImportProblem };

/** What can be made of what was picked: some photos, or one video. */
export function checkSelection(items: readonly PickedItem[]): Selection {
  const photos = items.filter((item) => item.kind === "photo");
  const videos = items.filter((item) => item.kind === "video");
  if (items.length === 0) return { ok: false, problem: "nothing" };
  if (videos.length > 1) return { ok: false, problem: "severalVideos" };
  const [video] = videos;
  if (video) {
    if (photos.length > 0) return { ok: false, problem: "photosAndVideo" };
    const durationMs = video.durationMs ?? 0;
    if (durationMs < MIN_VIDEO_MS) return { ok: false, problem: "videoTooShort" };
    if (durationMs > MAX_VIDEO_MS) return { ok: false, problem: "videoTooLong" };
    return { ok: true, video: { ...video, durationMs } };
  }
  if (photos.length > MAX_FRAMES) return { ok: false, problem: "tooManyPhotos" };
  return { ok: true, photos };
}

/**
 * When to take frames from a video: evenly through its length, never at the
 * very start or end, where a hand is still raising or lowering the phone.
 * About two a second at most, so a short clip gives fewer frames.
 */
export function frameTimesMs(durationMs: number, most = MAX_FRAMES): number[] {
  const count = Math.max(1, Math.min(most, Math.floor(durationMs / 500)));
  return Array.from({ length: count }, (_, i) => Math.round(((i + 0.5) * durationMs) / count));
}

export interface ImportedFrame {
  uri: string;
  /** Milliseconds into the video; for photos, their order. */
  atMs: number;
  widthPx: number;
  heightPx: number;
}

/** Photos in the order they were picked, a second apart so the order is kept. */
export function photoFrames(photos: readonly PickedItem[]): ImportedFrame[] {
  return photos.map((photo, index) => ({
    uri: photo.uri,
    atMs: index * 1000,
    widthPx: photo.widthPx,
    heightPx: photo.heightPx,
  }));
}

/** The capture to upload: keyframes without poses, and a one-line log that says where they came from. */
export function importedCapture(
  captureId: string,
  source: "photos" | "video",
  frames: readonly ImportedFrame[],
): LocalCapture {
  const [first] = frames;
  if (!first) throw new Error("An imported capture needs at least one picture");
  const recording = startRecording(0, { tracking: "none", lidar: false, depth: false });
  const state = {
    ...recording,
    // Sharpness 0: not measured on the phone. The server picks the best frames.
    keyframes: new Map(
      frames.map((frame, index) => [
        `import-${index + 1}`,
        { uri: frame.uri, atMs: frame.atMs, sharpness: 0, yaw: null, pitch: null },
      ]),
    ),
    sensorLog: [JSON.stringify({ t: 0, source: "import", from: source, pictures: frames.length })],
  };
  return {
    captureId,
    state,
    files: filesToUpload(state, { video: null, planes: null, sceneMesh: null, depth: null }),
    origin: "gallery",
    firstPictureSize: { width_px: first.widthPx, height_px: first.heightPx },
  };
}
