// Opens the phone's own photo picker and turns what was picked into a
// capture to upload. The system picker needs no permission to the whole
// library: the app only receives the items the person chose.
import { uuidV4 } from "@/capture/package/upload-capture";
import { resizePhotoForUpload } from "@/uploads/resize-photo";
import {
  checkSelection,
  frameTimesMs,
  type ImportedFrame,
  type ImportProblem,
  importedCapture,
  MAX_FRAMES,
  type PickedItem,
  photoFrames,
} from "./gallery-import";

export type PickResult =
  | { state: "cancelled" }
  | { state: "problem"; problem: ImportProblem }
  | { state: "picked"; capture: ReturnType<typeof importedCapture> };

const JPEG_QUALITY = 0.8;

/** Let the person choose photos or one video, and make the capture from them. */
export async function pickFromGallery(): Promise<PickResult> {
  const picker = await import("expo-image-picker");
  const result = await picker.launchImageLibraryAsync({
    mediaTypes: ["images", "videos"],
    allowsMultipleSelection: true,
    selectionLimit: MAX_FRAMES,
    quality: 1,
  });
  if (result.canceled) return { state: "cancelled" };
  const items: PickedItem[] = result.assets.map((asset) => ({
    uri: asset.uri,
    kind: asset.type === "video" ? "video" : "photo",
    widthPx: asset.width,
    heightPx: asset.height,
    ...(asset.duration ? { durationMs: asset.duration } : {}),
  }));
  const selection = checkSelection(items);
  if (!selection.ok) return { state: "problem", problem: selection.problem };

  if ("video" in selection) {
    const thumbnails = await import("expo-video-thumbnails");
    const frames: ImportedFrame[] = [];
    for (const atMs of frameTimesMs(selection.video.durationMs)) {
      const frame = await thumbnails.getThumbnailAsync(selection.video.uri, {
        time: atMs,
        quality: JPEG_QUALITY,
      });
      frames.push({ uri: frame.uri, atMs, widthPx: frame.width, heightPx: frame.height });
    }
    return { state: "picked", capture: importedCapture(uuidV4(), "video", frames) };
  }

  // Photos go up at the same size as any other photo, never the full sensor size.
  const resized: PickedItem[] = [];
  for (const photo of selection.photos) {
    const small = await resizePhotoForUpload(photo.uri, {
      width: photo.widthPx,
      height: photo.heightPx,
    });
    resized.push({ ...photo, uri: small.uri, widthPx: small.width, heightPx: small.height });
  }
  return { state: "picked", capture: importedCapture(uuidV4(), "photos", photoFrames(resized)) };
}
