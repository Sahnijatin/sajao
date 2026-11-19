import type { RoomContent } from "@/rooms/room-content";
import { useRoomData } from "./room-data";

describe("what the server said about rooms", () => {
  it("is forgotten for one room, so it is read again, and kept for the others", () => {
    const content = { sample: false } as RoomContent;
    useRoomData.getState().setContent("a", content);
    useRoomData.getState().setContent("b", content);
    useRoomData.getState().clearContent("a");
    expect(useRoomData.getState().content).toEqual({ b: content });
  });
});
