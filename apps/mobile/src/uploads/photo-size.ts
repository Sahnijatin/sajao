// Photos are resized on the phone before upload: about 1600 px on the long
// edge is plenty for room understanding and keeps uploads small on mobile data.
export const MAX_PHOTO_EDGE_PX = 1600;

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
