// The scan whose upload is not finished yet, kept in the phone's key-value
// storage so the upload resumes by itself the next time the app opens. One
// scan at a time: a new scan replaces the one before it.
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { LocalCapture } from "./native-capture";
import type { CaptureDeviceInfo } from "./upload-capture";

const KEY = "sajao.upload.pending";

export interface PendingUpload {
  local: LocalCapture;
  device: CaptureDeviceInfo;
}

export async function savePendingUpload(pending: PendingUpload): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(pending));
}

export async function loadPendingUpload(): Promise<PendingUpload | null> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingUpload>;
    return value.local?.captureId && value.local.files && value.device
      ? (value as PendingUpload)
      : null;
  } catch {
    return null;
  }
}

/** Forget the pending scan, but only if it is still this one. */
export async function clearPendingUpload(captureId: string): Promise<void> {
  const pending = await loadPendingUpload();
  if (pending?.local.captureId === captureId) await AsyncStorage.removeItem(KEY);
}
