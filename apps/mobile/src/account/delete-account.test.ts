import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRoomData } from "@/state/room-data";
import { useRooms } from "@/state/rooms";
import { useConsent } from "@/state/consent";
import { useTaste } from "@/state/taste";
import type { RoomContent } from "@/rooms/room-content";
import type { TasteAnswers } from "@/taste/taste-session";
import { deleteAccount, type DeleteDeps } from "./delete-account";

/** What is left on the phone: every stored key with what it holds, empty stores left out. */
async function leftOnPhone(): Promise<string[]> {
  const keys = await AsyncStorage.getAllKeys();
  const left: string[] = [];
  for (const key of keys) {
    const value = await AsyncStorage.getItem(key);
    const state = value ? (JSON.parse(value) as { state?: Record<string, unknown> }).state : null;
    // A store reset to empty writes its empty state back: that holds nothing of the person.
    const empty =
      state &&
      Object.values(state).every((v) => v === null || (Array.isArray(v) && v.length === 0));
    if (!empty) left.push(key);
  }
  return left.sort();
}

async function phoneWithData() {
  await AsyncStorage.clear();
  await AsyncStorage.setItem("sajao.settings", "{}");
  await AsyncStorage.setItem("sajao.rooms", "{}");
  await AsyncStorage.setItem("sajao.uploads.unfinished.x", "{}");
  await AsyncStorage.setItem("sb-auth-token", "session");
  useRooms.setState({ rooms: [] });
  useRooms.getState().addRoomForCapture("cap", 0, [{ id: "k1", uri: "file:///k1.jpg" }]);
  useRoomData.setState({ content: { cap: { sample: false } as RoomContent } });
  useTaste.setState({ answers: {} as TasteAnswers });
  useConsent.getState().accept(1);
}

const deps = (over: Partial<DeleteDeps> = {}): DeleteDeps & { removed: string[] } => {
  const removed: string[] = [];
  return {
    eraseOnServer: jest.fn(async () => {}),
    signOut: jest.fn(async () => {}),
    removeFile: (uri) => removed.push(uri),
    removed,
    ...over,
  };
};

describe("deleting your account", () => {
  it("erases it on the server, then everything on this phone except language and units", async () => {
    await phoneWithData();
    const d = deps();
    expect(await deleteAccount(d)).toBe("deleted");
    expect(d.eraseOnServer).toHaveBeenCalledTimes(1);
    expect(d.signOut).toHaveBeenCalledTimes(1);
    expect(d.removed).toEqual(["file:///k1.jpg"]);
    expect(await leftOnPhone()).toEqual(["sajao.settings"]);
    expect(useRooms.getState().rooms).toEqual([]);
    expect(useRoomData.getState().content).toEqual({});
    expect(useTaste.getState().answers).toBeNull();
    expect(useConsent.getState().acceptedVersion).toBeNull();
  });

  it("deletes nothing anywhere when the server cannot be reached", async () => {
    await phoneWithData();
    const d = deps({
      eraseOnServer: jest.fn(async () => {
        throw new Error("offline");
      }),
    });
    expect(await deleteAccount(d)).toBe("unreachable");
    expect(d.signOut).not.toHaveBeenCalled();
    expect(useRooms.getState().rooms).toHaveLength(1);
    expect(await AsyncStorage.getItem("sb-auth-token")).toBe("session");
    expect(await AsyncStorage.getItem("sajao.uploads.unfinished.x")).toBe("{}");
  });

  it("with no server in this build, clears this phone", async () => {
    await phoneWithData();
    expect(await deleteAccount(deps({ eraseOnServer: null }))).toBe("deleted");
    expect(useRooms.getState().rooms).toEqual([]);
  });

  it("still clears this phone when signing out fails after the server erased the account", async () => {
    await phoneWithData();
    const d = deps({
      signOut: jest.fn(async () => {
        throw new Error("no session");
      }),
    });
    expect(await deleteAccount(d)).toBe("deleted");
    expect(await leftOnPhone()).toEqual(["sajao.settings"]);
  });
});
