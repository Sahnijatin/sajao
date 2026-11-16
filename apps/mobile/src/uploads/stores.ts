// What an upload remembers across app restarts, kept in the phone's
// key-value storage: unfinished uploads (to resume them) and the storage
// keys of finished ones (to skip them).
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { UploadStateStore } from "./resumable-upload";

const UNFINISHED = "sajao.upload.unfinished:";
const FINISHED = "sajao.upload.finished:";
const MEDIA_ID = "sajao.capture.media:";

export const uploadStateStore: UploadStateStore = {
  async get(localId) {
    const raw = await AsyncStorage.getItem(UNFINISHED + localId);
    if (!raw) return null;
    try {
      const value = JSON.parse(raw) as { key?: unknown; upload_id?: unknown };
      return typeof value.key === "string" && typeof value.upload_id === "string"
        ? { key: value.key, upload_id: value.upload_id }
        : null;
    } catch {
      return null;
    }
  },
  set: (localId, state) => AsyncStorage.setItem(UNFINISHED + localId, JSON.stringify(state)),
  remove: (localId) => AsyncStorage.removeItem(UNFINISHED + localId),
};

export const finishedUploads = {
  get: (localId: string) => AsyncStorage.getItem(FINISHED + localId),
  set: (localId: string, key: string) => AsyncStorage.setItem(FINISHED + localId, key),
};

/** One stable id per capture for its media item, so a retry registers the same body. */
export async function mediaIdFor(captureId: string, make: () => string): Promise<string> {
  const known = await AsyncStorage.getItem(MEDIA_ID + captureId);
  if (known) return known;
  const id = make();
  await AsyncStorage.setItem(MEDIA_ID + captureId, id);
  return id;
}
