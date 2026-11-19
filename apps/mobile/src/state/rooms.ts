// The rooms on My home, saved on this phone. The API has no rooms endpoint
// yet; when it does, this store becomes a cache of it and nothing that reads
// rooms needs to change.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { clearSampleDesigns, newRoom, type Room, type RoomStill } from "@/rooms/rooms";

interface RoomsState {
  rooms: Room[];
  /** Adds the room for a scan. Adding the same scan twice keeps one room. */
  addRoomForCapture(captureId: string, atMs?: number): Room;
  /** The room's designs are ready: its card shows how many, and its hero still. */
  setRoomDesigns(roomId: string, designCount: number, still: RoomStill, atMs?: number): void;
  /** For a scan of several areas: which one to redesign. */
  setRedesignArea(roomId: string, areaId: string): void;
}

/** Saved rooms from an older build, brought up to this one. */
export function migrateRooms(saved: unknown, version: number): { rooms: Room[] } {
  const rooms = (saved as { rooms?: Room[] } | undefined)?.rooms ?? [];
  return { rooms: version < 2 ? clearSampleDesigns(rooms) : rooms };
}

export const useRooms = create<RoomsState>()(
  persist(
    (set, get) => ({
      rooms: [],
      addRoomForCapture(captureId, atMs = Date.now()) {
        const existing = get().rooms.find((room) => room.captureId === captureId);
        if (existing) return existing;
        const room = newRoom(get().rooms, { id: captureId, captureId, atMs });
        set({ rooms: [...get().rooms, room] });
        return room;
      },
      setRoomDesigns(roomId, designCount, still, atMs = Date.now()) {
        set({
          rooms: get().rooms.map((room) =>
            room.id === roomId ? { ...room, designCount, still, updatedAtMs: atMs } : room,
          ),
        });
      },
      setRedesignArea(roomId, areaId) {
        set({
          rooms: get().rooms.map((room) =>
            room.id === roomId ? { ...room, redesignAreaId: areaId } : room,
          ),
        });
      },
    }),
    {
      name: "sajao.rooms",
      version: 2,
      // Version 1 builds gave a room sample designs when no server answered.
      // Those were never the room's own, so they are cleared.
      migrate: migrateRooms,
      storage: createJSONStorage(() => AsyncStorage),
      partialize: ({ rooms }) => ({ rooms }),
    },
  ),
);

/** False until the saved rooms have been read, so the empty state never flashes first. */
export function useRoomsLoaded(): boolean {
  return useSyncExternalStore(
    (onChange) => useRooms.persist.onFinishHydration(onChange),
    () => useRooms.persist.hasHydrated(),
    () => useRooms.persist.hasHydrated(),
  );
}
