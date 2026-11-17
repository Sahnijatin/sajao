// Photos or a video already on the phone, as a way in beside the scan. The
// picking and the capture made from the pictures belong to the gallery
// import (src/import); this is the one place the app turns that into a room
// on My home and starts its upload, for both ways in: "Use photos or a
// video" on My home and the same offer on the scan screen. A room made this
// way is at the estimated level and says "measure to confirm".
import { Platform } from "react-native";
import { startCaptureUpload } from "@/capture/package/start-upload";
import type { ImportProblem } from "@/import/gallery-import";
import type { PickResult } from "@/import/pick";
import { previewScreensEnabled } from "@/preview-screens";
import { useCaptureStore } from "@/state/capture";
import { useRooms } from "@/state/rooms";

export type ImportResult =
  | { status: "imported"; roomId: string }
  | { status: "cancelled" }
  | { status: "problem"; problem: ImportProblem | "failed" };

/**
 * Whether My home offers "Use photos or a video". The pictures upload today,
 * but the server does not make a room from them yet, so the offer waits in
 * development and preview builds until it does.
 */
export function importOffered(): boolean {
  return previewScreensEnabled();
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
    useCaptureStore.getState().setLast(picked.capture);
    // The pictures become a room on My home at once, like a scan.
    const room = useRooms.getState().addRoomForCapture(picked.capture.captureId);
    void startCaptureUpload(picked.capture, {
      platform: Platform.OS === "ios" ? "ios" : "android",
      tier: "standard",
      has_ar: false,
    });
    return { status: "imported", roomId: room.id };
  } catch {
    return { status: "problem", problem: "failed" };
  }
}
