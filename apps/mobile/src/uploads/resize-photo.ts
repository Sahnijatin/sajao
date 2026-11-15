import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { type Size, uploadSize } from "./photo-size";

const JPEG_QUALITY = 0.8;

/** Resize a captured or picked photo for upload. Returns a new local JPEG file. */
export async function resizePhotoForUpload(uri: string, original: Size) {
  const target = uploadSize(original);
  const rendered = await ImageManipulator.manipulate(uri).resize(target).renderAsync();
  return rendered.saveAsync({ compress: JPEG_QUALITY, format: SaveFormat.JPEG });
}
