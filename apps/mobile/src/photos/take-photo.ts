// Camera glue for Take photos: a photo file from the camera, turned upright,
// resized like every other photo and checked to be landscape. The camera
// library writes orientation as metadata; decoding the file applies it, so
// the size read here is the size the person saw.
import type { ImageRef } from "expo-image-manipulator";
import { uploadSize } from "@/uploads/photo-size";
import { isLandscape, type TakenPhoto } from "./photo-session";

const JPEG_QUALITY = 0.8;

export type SavedPhoto = { ok: true; photo: TakenPhoto } | { ok: false; problem: "notLandscape" };

/** The upright, upload-sized JPEG of a photo the camera just wrote. */
export async function preparePhoto(fileUri: string): Promise<SavedPhoto> {
  const { ImageManipulator, SaveFormat } = await import("expo-image-manipulator");
  const upright: ImageRef = await ImageManipulator.manipulate(fileUri).renderAsync();
  if (!isLandscape({ widthPx: upright.width, heightPx: upright.height })) {
    return { ok: false, problem: "notLandscape" };
  }
  const size = uploadSize({ width: upright.width, height: upright.height });
  const resized = await ImageManipulator.manipulate(upright).resize(size).renderAsync();
  const saved = await resized.saveAsync({ compress: JPEG_QUALITY, format: SaveFormat.JPEG });
  return { ok: true, photo: { uri: saved.uri, widthPx: saved.width, heightPx: saved.height } };
}

/** "file:///..." for a path the camera library returns without a scheme. */
export function fileUri(path: string): string {
  return path.startsWith("file://") ? path : `file://${path}`;
}
