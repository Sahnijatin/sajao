import { migrateRooms, useRooms } from "./rooms";
import type { Room } from "@/rooms/rooms";

const room = (over: Partial<Room>): Room => ({
  id: "a",
  name: null,
  number: 1,
  updatedAtMs: 0,
  designCount: 0,
  still: { kind: "placeholder", look: "before" },
  captureId: "c",
  ...over,
});

describe("saved rooms from an older build", () => {
  it("lose the sample designs an older build gave them, and keep everything else", () => {
    const sampled = room({
      id: "s",
      name: "Den",
      designCount: 3,
      still: { kind: "placeholder", look: "after", view: 1 },
    });
    const real = room({
      id: "r",
      designCount: 3,
      still: { kind: "image", uri: "https://x/hero.jpg" },
    });
    const plain = room({ id: "p" });
    expect(migrateRooms({ rooms: [sampled, real, plain] }, 1).rooms).toEqual([
      { ...sampled, designCount: 0, still: { kind: "placeholder", look: "before" } },
      real,
      plain,
    ]);
  });

  it("are left alone from this build on, and nothing saved is no rooms", () => {
    const sampled = room({ designCount: 3, still: { kind: "placeholder", look: "after" } });
    expect(migrateRooms({ rooms: [sampled] }, 2).rooms).toEqual([sampled]);
    expect(migrateRooms(undefined, 0).rooms).toEqual([]);
  });
});

describe("a room's design ids", () => {
  it("are made once and kept, so asking again is the same request", () => {
    useRooms.setState({ rooms: [] });
    let n = 0;
    const newId = () => `id-${(n += 1)}`;
    const room = useRooms.getState().addRoomForCapture("cap", 0, ["file:///a.jpg"]);
    expect(room.photos).toEqual(["file:///a.jpg"]);
    const first = useRooms.getState().designIdsFor(room.id, newId, new Date(0));
    expect(first).toEqual({
      requestId: "id-1",
      briefId: "id-2",
      spaceProfileId: "id-3",
      tasteProfileId: "id-4",
      createdAt: "1970-01-01T00:00:00.000Z",
    });
    expect(useRooms.getState().designIdsFor(room.id, newId)).toEqual(first);
    expect(useRooms.getState().designIdsFor("nope", newId)).toBeNull();
  });
});

describe("measuring a room again", () => {
  it("points the room at the new scan and asks for its designs afresh, keeping its name and photos", () => {
    useRooms.setState({ rooms: [] });
    const room = useRooms.getState().addRoomForCapture("old", 0, ["file:///a.jpg"]);
    useRooms.getState().designIdsFor(room.id, () => "id", new Date(0));
    useRooms.getState().setRoomDesigns(room.id, 3, { kind: "image", uri: "file:///a.jpg" }, 1);
    useRooms.getState().setRedesignArea(room.id, "a1");
    useRooms.setState({
      rooms: useRooms.getState().rooms.map((each) => ({ ...each, name: "Den" })),
    });
    useRooms.getState().remeasure(room.id, "new", 5);
    const after = useRooms.getState().rooms[0];
    expect(after).toMatchObject({
      id: room.id,
      name: "Den",
      captureId: "new",
      designCount: 0,
      still: { kind: "placeholder", look: "before" },
      updatedAtMs: 5,
      photos: ["file:///a.jpg"],
    });
    expect(after?.designIds).toBeUndefined();
    expect(after?.redesignAreaId).toBeUndefined();
    expect(useRooms.getState().rooms).toHaveLength(1);
  });
});
