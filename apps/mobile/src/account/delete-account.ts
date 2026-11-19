// Deleting your account and data, as both stores require. The server erases
// the account and everything stored for it (DELETE /v1/me, safe to repeat);
// then this phone forgets the session and everything it kept. If the server
// cannot be reached nothing is deleted anywhere, so the person can try again.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCaptureStore } from "@/state/capture";
import { useRoomData } from "@/state/room-data";
import { useRooms } from "@/state/rooms";
import { useTaste } from "@/state/taste";

/** Kept on the phone: language and units say nothing about the person. */
export const KEPT_KEYS: readonly string[] = ["sajao.settings"];

export type DeleteResult = "deleted" | "unreachable";

export interface DeleteDeps {
  /** Asks the server to erase the account; null when this build has no server. */
  eraseOnServer: (() => Promise<void>) | null;
  /** Forgets the sign-in session on this phone. */
  signOut: () => Promise<void>;
  /** Removes a file this phone kept, such as a room photo. */
  removeFile: (uri: string) => void;
}

/** Everything this phone kept for the person: stored keys, files and what is in memory. */
export async function wipeLocal(removeFile: DeleteDeps["removeFile"]): Promise<void> {
  for (const room of useRooms.getState().rooms) {
    for (const photo of room.photos ?? []) {
      try {
        removeFile(photo.uri);
      } catch {
        // Already gone, or the system cleared it: nothing left to remove.
      }
    }
  }
  const keys = await AsyncStorage.getAllKeys();
  await AsyncStorage.multiRemove(keys.filter((key) => !KEPT_KEYS.includes(key)));
  useRooms.setState({ rooms: [] });
  useRoomData.setState({ content: {} });
  useTaste.setState({ answers: null, lastBudget: null });
  useCaptureStore.setState({
    last: null,
    missing: null,
    room: null,
    upload: { state: "idle", finished: 0, total: 0 },
  });
}

/** Erase the account on the server, then everything on this phone. */
export async function deleteAccount(deps: DeleteDeps): Promise<DeleteResult> {
  if (deps.eraseOnServer) {
    try {
      await deps.eraseOnServer();
    } catch {
      return "unreachable";
    }
  }
  try {
    await deps.signOut();
  } catch {
    // The account is gone on the server; the stored session is removed below anyway.
  }
  await wipeLocal(deps.removeFile);
  return "deleted";
}
