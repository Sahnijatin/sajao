import { migrateRooms } from "./rooms";
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
