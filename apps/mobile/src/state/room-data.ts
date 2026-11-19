// What the server has told this phone about its rooms, in memory: a room's
// content once its twin is read. Read again from the server when the app
// next opens the room; nothing here is the source of truth.
import { create } from "zustand";
import type { RoomContent } from "@/rooms/room-content";

interface RoomData {
  content: Record<string, RoomContent>;
  setContent(roomId: string, content: RoomContent): void;
  /** Forget what the server said about a room, so it is read again. */
  clearContent(roomId: string): void;
}

export const useRoomData = create<RoomData>((set) => ({
  content: {},
  setContent: (roomId, content) =>
    set((state) => ({ content: { ...state.content, [roomId]: content } })),
  clearContent: (roomId) =>
    set((state) => {
      const { [roomId]: _gone, ...rest } = state.content;
      return { content: rest };
    }),
}));
