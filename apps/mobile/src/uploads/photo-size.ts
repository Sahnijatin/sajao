// Photos are resized on the phone before upload: at least 2048 px on the
// long edge (a 4:3 photo goes up at 2048 by 1536), so the room's walls,
// doors and objects keep their detail for measuring and redesigning. The
// server asks for no smaller size; a photo already smaller is never enlarged.
export const MAX_PHOTO_EDGE_PX = 2048;

/** JPEG quality for uploaded photos: high, as the photo is the room's ground truth. */
export const PHOTO_JPEG_QUALITY = 0.9;

export interface Size {
  width: number;
  height: number;
}

/** The size to upload at. Never enlarges, and keeps the aspect ratio. */
export function uploadSize(original: Size, maxEdge: number = MAX_PHOTO_EDGE_PX): Size {
  const longEdge = Math.max(original.width, original.height);
  if (longEdge <= maxEdge) return { width: original.width, height: original.height };
  const scale = maxEdge / longEdge;
  return {
    width: Math.max(1, Math.round(original.width * scale)),
    height: Math.max(1, Math.round(original.height * scale)),
  };
}
