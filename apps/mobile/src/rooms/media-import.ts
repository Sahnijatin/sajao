// Photos or a video already on the phone, as a way in beside the scan. The
// picking and the capture made from the pictures belong to the gallery
// import (src/import); this is the one place the app turns that into a room
// on My home and starts its upload, for both ways in: "Use photos or a
// video" on My home and the same offer on the scan screen. A room made this
// way is at the estimated level and says "measure to confirm".
import { Platform } from "react-native";
import type { LocalCapture } from "@/capture/package/native-capture";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { uuidV4 } from "@/capture/package/upload-capture";
import { type ImportProblem, importedCapture } from "@/import/gallery-import";
import type { PickResult } from "@/import/pick";
import { keptFrames, type TakenPhoto } from "@/photos/photo-session";
import { useCaptureStore } from "@/state/capture";
import { useRooms } from "@/state/rooms";

export type ImportResult =
  | { status: "imported"; roomId: string }
  | { status: "cancelled" }
  | { status: "problem"; problem: ImportProblem | "failed" };

/** Make a room on My home from a capture with no AR data, and start its upload. */
function startRoom(capture: LocalCapture): string {
  useCaptureStore.getState().setLast(capture);
  // The pictures become a room on My home at once, like a scan.
  const room = useRooms.getState().addRoomForCapture(
    capture.captureId,
    Date.now(),
    capture.files.keyframes.map((frame) => ({ id: frame.id, uri: frame.uri })),
  );
  void startCaptureUpload(capture, {
    platform: Platform.OS === "ios" ? "ios" : "android",
    tier: "standard",
    has_ar: false,
  });
  return room.id;
}

/** Photos taken in the app with Take photos: a room on My home, uploading. Returns its id. */
export function startPhotoRoom(
  photos: readonly TakenPhoto[],
  captureId: string = uuidV4(),
): string {
  return startRoom(importedCapture(captureId, "camera", keptFrames(photos)));
}

async function pickFromPhone(): Promise<PickResult> {
  // Loaded here, not at the top: a build from before the picker was added
  // must still open, and say so when this is tapped.
  const { pickFromGallery } = await import("@/import/pick");
  return pickFromGallery();
}

/** Choose photos or one video, make them a room on My home, and start the upload. */
export async function importFromGallery(
  pick: () => Promise<PickResult> = pickFromPhone,
): Promise<ImportResult> {
  try {
    const picked = await pick();
    if (picked.state === "cancelled") return { status: "cancelled" };
    if (picked.state === "problem") return { status: "problem", problem: picked.problem };
    return { status: "imported", roomId: startRoom(picked.capture) };
  } catch {
    return { status: "problem", problem: "failed" };
  }
}
