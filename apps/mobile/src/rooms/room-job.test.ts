import { followRoom, isSettled, type RoomJob, roomMessage } from "./room-job";

const job = (measure: string, detail: string | null = null): RoomJob => ({
  id: "room-1",
  status: measure === "failed" ? "failed" : "working",
  stages: [
    { stage: "measure", status: measure, detail },
    { stage: "inventory", status: "queued" },
  ],
});

function follow(reads: RoomJob[], giveUpAfterMs?: number) {
  const seen: RoomJob[] = [];
  let clock = 0;
  const api = {
    create: jest.fn(async () => job("queued")),
    read: jest.fn(async () => reads.shift() ?? job("running")),
  };
  const result = followRoom(api, "capture-1", {
    onUpdate: (room) => seen.push(room),
    sleep: async (ms) => {
      clock += ms;
    },
    now: () => clock,
    ...(giveUpAfterMs ? { giveUpAfterMs } : {}),
  });
  return { api, seen, result };
}

describe("following a room", () => {
  it("creates the room for the capture and follows it until it is measured", async () => {
    const { api, seen, result } = follow([job("running"), job("done")]);
    const room = await result;
    expect(api.create).toHaveBeenCalledWith("capture-1");
    expect(api.read).toHaveBeenCalledTimes(2);
    expect(seen.map((r) => r.stages[0]?.status)).toEqual(["queued", "running", "done"]);
    expect(isSettled(room)).toBe(true);
  });

  it("stops at a failure and keeps its reason", async () => {
    const { api, result } = follow([job("failed", "no_walls")]);
    const room = await result;
    expect(api.read).toHaveBeenCalledTimes(1);
    expect(roomMessage(room)).toBe("home.room.failed.no_walls");
  });

  it("stops asking after a while; the room carries on at the server", async () => {
    const { api, result } = follow([], 6000);
    const room = await result;
    expect(api.read).toHaveBeenCalledTimes(3);
    expect(roomMessage(room)).toBe("home.room.measuring");
  });
});

describe("room message", () => {
  it("says measuring, then measured", () => {
    expect(roomMessage(job("queued"))).toBe("home.room.measuring");
    expect(roomMessage(job("running"))).toBe("home.room.measuring");
    expect(roomMessage(job("done"))).toBe("home.room.measured");
  });

  it("uses the general text for a reason it has no words for", () => {
    expect(roomMessage(job("failed", "stage_failed"))).toBe("home.room.failed.other");
    expect(roomMessage(job("failed", "no_ar_data"))).toBe("home.room.failed.no_ar_data");
    expect(roomMessage(job("failed"))).toBe("home.room.failed.other");
  });
});
