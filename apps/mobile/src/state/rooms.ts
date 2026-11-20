// The rooms on My home, saved on this phone. The API has no rooms endpoint
// yet; when it does, this store becomes a cache of it and nothing that reads
// rooms needs to change.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { DesignIds } from "@/rooms/designs-api";
import {
  clearSampleDesigns,
  newRoom,
  type Room,
  type RoomPhoto,
  type RoomStill,
} from "@/rooms/rooms";

interface RoomsState {
  rooms: Room[];
  /**
   * Adds the room for a scan. Adding the same scan twice keeps one room.
   * Photos, when given, are the person's own pictures of it.
   */
  addRoomForCapture(captureId: string, atMs?: number, photos?: readonly RoomPhoto[]): Room;
  /** The room's designs are ready: its card shows how many, and its hero still. */
  setRoomDesigns(roomId: string, designCount: number, still: RoomStill, atMs?: number): void;
  /** For a scan of several areas: which one to redesign. */
  setRedesignArea(roomId: string, areaId: string): void;
  /** The budget this room's designs are asked for with. */
  setRoomBudget(roomId: string, budget: NonNullable<Room["budget"]>): void;
  /**
   * The room is being measured again with a new scan. The room keeps all it
   * has until the new scan is done (`finishRemeasure`) or fails (`abandonRemeasure`).
   */
  remeasure(roomId: string, captureId: string, photos?: readonly RoomPhoto[]): void;
  /** The new scan is measured and has its designs: the room follows it from now on. */
  finishRemeasure(roomId: string, atMs?: number): void;
  /** The new scan failed or was given up: the room stays exactly as it was. */
  abandonRemeasure(roomId: string): void;
  /**
   * The ids the room's designs are asked for with, made on first use and
   * kept: the new scan's own while the room is being measured again.
   */
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
      remeasure(roomId, captureId, photos) {
        set({
          rooms: get().rooms.map((room) =>
            room.id === roomId
              ? { ...room, remeasure: { captureId, ...(photos ? { photos: [...photos] } : {}) } }
              : room,
          ),
        });
      },
      finishRemeasure(roomId, atMs = Date.now()) {
        set({
          rooms: get().rooms.map((room) => {
            if (room.id !== roomId || !room.remeasure) return room;
            const { remeasure, designIds: _designs, redesignAreaId: _area, ...kept } = room;
            return {
              ...kept,
              captureId: remeasure.captureId,
              ...(remeasure.photos ? { photos: remeasure.photos } : {}),
              ...(remeasure.designIds ? { designIds: remeasure.designIds } : {}),
              // The new designs, if any, are set on the card right after.
              designCount: 0,
              still: { kind: "placeholder", look: "before" },
              updatedAtMs: atMs,
            };
          }),
        });
      },
      abandonRemeasure(roomId) {
        set({
          rooms: get().rooms.map((room) => {
            if (room.id !== roomId) return room;
            const { remeasure: _gone, ...kept } = room;
            return kept;
          }),
        });
      },
      designIdsFor(roomId, newId, now = new Date()) {
        const room = get().rooms.find((each) => each.id === roomId);
        if (!room) return null;
        const held = room.remeasure ? room.remeasure.designIds : room.designIds;
        if (held) return held;
        const designIds: DesignIds = {
          requestId: newId(),
          briefId: newId(),
          spaceProfileId: newId(),
          tasteProfileId: newId(),
          createdAt: now.toISOString(),
        };
        set({
          rooms: get().rooms.map((each) => {
            if (each.id !== roomId) return each;
            return each.remeasure
              ? { ...each, remeasure: { ...each.remeasure, designIds } }
              : { ...each, designIds };
          }),
        });
        return designIds;
      },
      setRoomBudget(roomId, budget) {
        set({
          rooms: get().rooms.map((room) => (room.id === roomId ? { ...room, budget } : room)),
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
