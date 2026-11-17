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

// The recorder keeps keyframes and poses in Maps, which JSON would write as
// empty objects: they are stored as lists of entries and rebuilt on load.
interface Stored {
  local: Omit<LocalCapture, "state"> & {
    state: Omit<LocalCapture["state"], "keyframes" | "poses"> & {
      keyframes: [string, unknown][];
      poses: [string, unknown][];
    };
  };
  device: CaptureDeviceInfo;
}

export async function savePendingUpload(pending: PendingUpload): Promise<void> {
  const { state } = pending.local;
  const stored: Stored = {
    device: pending.device,
    local: {
      ...pending.local,
      state: { ...state, keyframes: [...state.keyframes], poses: [...state.poses] },
    },
  };
  await AsyncStorage.setItem(KEY, JSON.stringify(stored));
}

export async function loadPendingUpload(): Promise<PendingUpload | null> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<Stored>;
    const local = value.local;
    if (!local?.captureId || !local.files || !value.device) return null;
    if (!Array.isArray(local.state?.keyframes) || !Array.isArray(local.state.poses)) return null;
    return {
      device: value.device,
      local: {
        ...local,
        state: {
          ...local.state,
          keyframes: new Map(local.state.keyframes),
          poses: new Map(local.state.poses),
        },
      } as LocalCapture,
    };
  } catch {
    return null;
  }
}

/** Forget the pending scan, but only if it is still this one. */
export async function clearPendingUpload(captureId: string): Promise<void> {
  const pending = await loadPendingUpload();
  if (pending?.local.captureId === captureId) await AsyncStorage.removeItem(KEY);
}
