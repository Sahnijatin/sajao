// Photos and videos already on the phone, as a way in beside the scan. A
// room made from them is measured at the "estimated" level and says
// "measure to confirm". This file is the app's side only: choosing the
// media, and the hand-off to the importer that sends it to the same
// pipeline as a scan. The importer belongs with the upload code; until one
// is registered the way in shows only in development and preview builds.
import { previewScreensEnabled } from "@/preview-screens";

export interface PickedMedia {
  uri: string;
  kind: "photo" | "video";
  /** Seconds, for a video. */
  durationS: number | null;
}

/** The most photos and videos one room can be made from. */
export const MAX_MEDIA = 20;

/** Sends the chosen media to the pipeline; resolves with the new room's id. */
export type MediaImporter = (media: readonly PickedMedia[]) => Promise<{ roomId: string }>;

let importer: MediaImporter | null = null;

/** Called once by the upload code when it can take photos and videos. */
export function registerMediaImporter(next: MediaImporter | null): void {
  importer = next;
}

export function mediaImporter(): MediaImporter | null {
  return importer;
}

/** Whether "Use photos or a video" is offered: when it leads somewhere, or in a build for trying things. */
export function importOffered(): boolean {
  return importer !== null || previewScreensEnabled();
}

export type PickResult =
  | { status: "picked"; media: PickedMedia[] }
  | { status: "cancelled" }
  /** The phone said no to the photo library. */
  | { status: "denied" }
  /** This build was made before the picker was added. */
  | { status: "unavailable" };

export interface Picker {
  requestMediaLibraryPermissionsAsync(): Promise<{ granted: boolean }>;
  launchImageLibraryAsync(options: Record<string, unknown>): Promise<{
    canceled: boolean;
    assets?: { uri: string; type?: string | null; duration?: number | null }[] | null;
  }>;
}

async function loadPicker(): Promise<Picker | null> {
  try {
    // Loaded here, not at the top: an installed build from before the picker
    // was added must still open, and say so when this is tapped.
    return (await import("expo-image-picker")) as unknown as Picker;
  } catch {
    return null;
  }
}

/** Opens the phone's own photo picker for photos and videos. */
export async function pickMedia(
  load: () => Promise<Picker | null> = loadPicker,
): Promise<PickResult> {
  const picker = await load();
  if (!picker) return { status: "unavailable" };
  try {
    const permission = await picker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return { status: "denied" };
    const result = await picker.launchImageLibraryAsync({
      mediaTypes: ["images", "videos"],
      allowsMultipleSelection: true,
      selectionLimit: MAX_MEDIA,
      // The files go up as they are: nothing is cropped or recompressed here.
      allowsEditing: false,
      quality: 1,
    });
    if (result.canceled || !result.assets?.length) return { status: "cancelled" };
    return {
      status: "picked",
      media: result.assets.slice(0, MAX_MEDIA).map((asset) => ({
        uri: asset.uri,
        kind: asset.type === "video" ? "video" : "photo",
        durationS: asset.type === "video" && asset.duration ? asset.duration / 1000 : null,
      })),
    };
  } catch {
    return { status: "unavailable" };
  }
}
