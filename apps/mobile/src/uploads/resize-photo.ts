import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { PHOTO_JPEG_QUALITY, type Size, uploadSize } from "./photo-size";

/** Resize a captured or picked photo for upload. Returns a new local JPEG file. */
export async function resizePhotoForUpload(uri: string, original: Size) {
  const target = uploadSize(original);
  const rendered = await ImageManipulator.manipulate(uri).resize(target).renderAsync();
  return rendered.saveAsync({ compress: PHOTO_JPEG_QUALITY, format: SaveFormat.JPEG });
}
