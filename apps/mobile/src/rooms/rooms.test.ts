import { designsLabel, newRoom, nextRoomNumber, type Room, sortRooms, updatedLabel } from "./rooms";

const room = (over: Partial<Room>): Room => ({
  id: "a",
  name: null,
  number: 1,
  updatedAtMs: 0,
  designCount: 0,
  still: { kind: "placeholder", look: "before" },
  captureId: null,
  ...over,
});

const at = (day: number, hour = 12) => new Date(2026, 0, day, hour).getTime();

describe("rooms", () => {
  it("lists the most recently updated room first", () => {
    const rooms = [
      room({ id: "old", updatedAtMs: 1 }),
      room({ id: "new", updatedAtMs: 3 }),
      room({ id: "mid", updatedAtMs: 2 }),
    ];
    expect(sortRooms(rooms).map((r) => r.id)).toEqual(["new", "mid", "old"]);
  });

  it("numbers a new room one past the highest, even after a room is removed", () => {
    expect(nextRoomNumber([])).toBe(1);
    expect(nextRoomNumber([room({ number: 1 }), room({ number: 4 })])).toBe(5);
  });

  it("starts a new room with no name, no designs and a stand-in still", () => {
    expect(newRoom([room({ number: 2 })], { id: "r", captureId: "c", atMs: 9 })).toEqual({
      id: "r",
      name: null,
      number: 3,
      updatedAtMs: 9,
      designCount: 0,
      still: { kind: "placeholder", look: "before" },
      captureId: "c",
    });
  });
});

describe("card labels", () => {
  it("says when the room was last updated, by calendar day", () => {
    expect(updatedLabel(at(10, 9), at(10, 23))).toEqual({ key: "rooms.updated.today" });
    // Late last night is yesterday, not "today", even though it is under 24 hours ago.
    expect(updatedLabel(at(9, 23), at(10, 1))).toEqual({ key: "rooms.updated.yesterday" });
    expect(updatedLabel(at(5), at(10))).toEqual({
      key: "rooms.updated.daysAgo",
      values: { count: 5 },
    });
    expect(updatedLabel(at(1), at(40))).toEqual({ key: "rooms.updated.lastMonth" });
    expect(updatedLabel(at(1), at(100))).toEqual({
      key: "rooms.updated.monthsAgo",
      values: { count: 3 },
    });
  });

  it("treats a clock that moved backwards as today", () => {
    expect(updatedLabel(at(12), at(10))).toEqual({ key: "rooms.updated.today" });
  });

  it("counts designs, or says there are none yet", () => {
    expect(designsLabel(0)).toEqual({ key: "rooms.designs.none" });
    expect(designsLabel(3)).toEqual({ key: "rooms.designs.count", values: { count: 3 } });
  });
});
