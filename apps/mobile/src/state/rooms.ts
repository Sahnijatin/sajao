// The rooms on My home, saved on this phone. The API has no rooms endpoint
// yet; when it does, this store becomes a cache of it and nothing that reads
// rooms needs to change.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { DesignIds } from "@/rooms/designs-api";
import { clearSampleDesigns, newRoom, type Room, type RoomStill } from "@/rooms/rooms";

interface RoomsState {
  rooms: Room[];
  /**
   * Adds the room for a scan. Adding the same scan twice keeps one room.
   * Photos, when given, are the person's own pictures of it.
   */
  addRoomForCapture(captureId: string, atMs?: number, photos?: readonly string[]): Room;
  /** The room's designs are ready: its card shows how many, and its hero still. */
  setRoomDesigns(roomId: string, designCount: number, still: RoomStill, atMs?: number): void;
  /** For a scan of several areas: which one to redesign. */
  setRedesignArea(roomId: string, areaId: string): void;
  /**
   * The room was measured again with a new scan: it follows that scan from
   * now on, and its designs are asked for afresh. Its name and photos stay.
   */
  remeasure(roomId: string, captureId: string, atMs?: number): void;
  /** The ids the room's designs are asked for with, made on first use and kept. */
  designIdsFor(roomId: string, newId: () => string, now?: Date): DesignIds | null;
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
      addRoomForCapture(captureId, atMs = Date.now(), photos) {
        const existing = get().rooms.find((room) => room.captureId === captureId);
        if (existing) return existing;
        const room: Room = {
          ...newRoom(get().rooms, { id: captureId, captureId, atMs }),
          ...(photos && photos.length > 0 ? { photos: [...photos] } : {}),
        };
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
      remeasure(roomId, captureId, atMs = Date.now()) {
        set({
          rooms: get().rooms.map((room) => {
            if (room.id !== roomId) return room;
            const { designIds: _designs, redesignAreaId: _area, ...kept } = room;
            return {
              ...kept,
              captureId,
              designCount: 0,
              still: { kind: "placeholder", look: "before" },
              updatedAtMs: atMs,
            };
          }),
        });
      },
      designIdsFor(roomId, newId, now = new Date()) {
        const room = get().rooms.find((each) => each.id === roomId);
        if (!room) return null;
        if (room.designIds) return room.designIds;
        const designIds: DesignIds = {
          requestId: newId(),
          briefId: newId(),
          spaceProfileId: newId(),
          tasteProfileId: newId(),
          createdAt: now.toISOString(),
        };
        set({
          rooms: get().rooms.map((each) => (each.id === roomId ? { ...each, designIds } : each)),
        });
        return designIds;
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
