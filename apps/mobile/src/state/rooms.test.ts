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
    const room = useRooms
      .getState()
      .addRoomForCapture("cap", 0, [{ id: "k1", uri: "file:///a.jpg" }]);
    expect(room.photos).toEqual([{ id: "k1", uri: "file:///a.jpg" }]);
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

describe("a room's budget", () => {
  it("is kept with the room", () => {
    useRooms.setState({ rooms: [] });
    const room = useRooms.getState().addRoomForCapture("cap", 0);
    const budget = {
      limit: { currency: "INR", amount_minor: 100 },
      flexibility: "strict",
    } as const;
    useRooms.getState().setRoomBudget(room.id, budget);
    expect(useRooms.getState().rooms[0]?.budget).toEqual(budget);
  });
});

describe("measuring a room again", () => {
  function roomWithDesigns() {
    useRooms.setState({ rooms: [] });
    const room = useRooms
      .getState()
      .addRoomForCapture("old", 0, [{ id: "k1", uri: "file:///a.jpg" }]);
    useRooms.getState().designIdsFor(room.id, () => "old-id", new Date(0));
    useRooms.getState().setRoomDesigns(room.id, 3, { kind: "image", uri: "file:///a.jpg" }, 1);
    useRooms.getState().setRedesignArea(room.id, "a1");
    return useRooms.getState().rooms[0]!;
  }

  it("keeps everything the room has while the new scan is worked on, with its own design ids", () => {
    const before = roomWithDesigns();
    useRooms.getState().remeasure(before.id, "new");
    const ids = useRooms.getState().designIdsFor(before.id, () => "new-id", new Date(0));
    expect(ids?.requestId).toBe("new-id");
    const during = useRooms.getState().rooms[0]!;
    expect(during).toEqual({
      ...before,
      remeasure: { captureId: "new", designIds: ids },
    });
  });

  it("follows the new scan once it is done, keeping its name, photos and budget", () => {
    const before = roomWithDesigns();
    useRooms.getState().remeasure(before.id, "new");
    useRooms.getState().designIdsFor(before.id, () => "new-id", new Date(0));
    useRooms.getState().finishRemeasure(before.id, 5);
    const after = useRooms.getState().rooms[0]!;
    expect(after).toMatchObject({
      id: before.id,
      captureId: "new",
      designCount: 0,
      updatedAtMs: 5,
      photos: [{ id: "k1", uri: "file:///a.jpg" }],
    });
    expect(after.designIds?.requestId).toBe("new-id");
    expect(after.remeasure).toBeUndefined();
    expect(after.redesignAreaId).toBeUndefined();
  });

  it("loses nothing when the new scan fails", () => {
    const before = roomWithDesigns();
    useRooms.getState().remeasure(before.id, "new");
    useRooms.getState().abandonRemeasure(before.id);
    expect(useRooms.getState().rooms[0]).toEqual(before);
    // Finishing with nothing pending changes nothing.
    useRooms.getState().finishRemeasure(before.id);
    expect(useRooms.getState().rooms[0]).toEqual(before);
  });
});
