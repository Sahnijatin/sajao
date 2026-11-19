import type { Design, SpaceTwin } from "@sajao/schemas";
import designFixture from "../../../../packages/schemas/fixtures/v1/valid/design.json";
import twinFixture from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import { useCaptureStore } from "@/state/capture";
import { useRoomData } from "@/state/room-data";
import { useRoomJobs } from "@/state/room-jobs";
import { useRooms } from "@/state/rooms";
import { useTaste } from "@/state/taste";
import type { TasteAnswers } from "@/taste/taste-session";
import type { DesignsJob } from "./designs-api";
import { POLL_MS, type RoomApi, type RoomJob } from "./room-api";
import { type RoomContent, sampleContent } from "./room-content";

const mockApi: { current: RoomApi | null } = { current: null };
// The source makes its client once, so the client hands each call to the test's current fake.
jest.mock("./room-client", () => ({
  roomApi: () => ({
    createRoom: (...args: [string]) => mockApi.current!.createRoom(...args),
    getRoom: (...args: [string]) => mockApi.current!.getRoom(...args),
    getTwin: (...args: [string]) => mockApi.current!.getTwin(...args),
    requestDesigns: (...args: [string, never]) => mockApi.current!.requestDesigns(...args),
    getDesigns: (...args: [string]) => mockApi.current!.getDesigns(...args),
  }),
}));
jest.mock("@/preview-screens", () => ({ previewScreensEnabled: () => true }));

// Loaded after the mock so the source picks up the fake API.
const { loadRoomContent, retryRoomJob, roomGeneration, startRoomJob } =
  jest.requireActual<typeof import("./room-source")>("./room-source");

const ready: RoomJob = {
  id: "server-new",
  status: "ready",
  stages: [
    { stage: "measure", status: "done" },
    { stage: "inventory", status: "done" },
  ],
};
const failedJob: RoomJob = {
  id: "server-new",
  status: "failed",
  stages: [{ stage: "measure", status: "failed", detail: "no_walls" }],
};
const design = designFixture as unknown as Design;
const three = (["best_value", "best_match", "bold"] as const).map((slot) => ({
  ...design,
  id: `new-${slot}`,
  slot,
}));
const designsReady: DesignsJob = { id: "req", status: "ready", stages: [], designs: three };

function fakeApi(job: RoomJob, designs: DesignsJob = designsReady): RoomApi {
  return {
    createRoom: jest.fn(async () => job),
    getRoom: jest.fn(async () => job),
    getTwin: jest.fn(async () => twinFixture as unknown as SpaceTwin),
    requestDesigns: jest.fn(async () => ({ ...designs, status: "working" })),
    getDesigns: jest.fn(async () => designs),
  };
}

const old = { ...(sampleContent() as RoomContent), sample: false };

function roomBeingMeasured() {
  useRooms.setState({ rooms: [] });
  const room = useRooms.getState().addRoomForCapture("old-capture", 0);
  useRooms.getState().setRoomDesigns(room.id, 3, { kind: "image", uri: "file:///a.jpg" }, 0);
  useRoomData.setState({ content: { [room.id]: old } });
  useRooms.getState().remeasure(room.id, "new-capture");
  useCaptureStore.setState({
    last: { captureId: "new-capture" } as never,
    upload: { state: "done", finished: 1, total: 1 },
  });
  useTaste.setState({
    answers: {
      budget: { limit: { currency: "INR", amount_minor: 100 }, flexibility: "strict" },
      must_haves: [],
      consider_vastu: false,
    } as unknown as TasteAnswers,
  });
  return room.id;
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

describe("measuring a room again", () => {
  it("keeps the old designs on show until the new scan's designs arrive, then swaps them in", async () => {
    const id = roomBeingMeasured();
    mockApi.current = fakeApi(ready, { id: "req", status: "working", stages: [] });
    const finished: number[] = [];
    roomGeneration()!.watch(id, (count) => finished.push(count));
    await jest.advanceTimersByTimeAsync(0);
    // Measured, designs still coming: the room still shows the old ones.
    expect(useRoomData.getState().content[id]).toBe(old);
    expect(useRooms.getState().rooms[0]?.captureId).toBe("old-capture");
    (mockApi.current.getDesigns as jest.Mock).mockResolvedValue(designsReady);
    await jest.advanceTimersByTimeAsync(POLL_MS);
    expect(finished.at(-1)).toBe(3);
    const now = useRoomData.getState().content[id]!;
    expect(now.looks.map((look) => look.design.id)).toEqual([
      "new-best_value",
      "new-best_match",
      "new-bold",
    ]);
    const room = useRooms.getState().rooms[0]!;
    expect(room.captureId).toBe("new-capture");
    expect(room.remeasure).toBeUndefined();
    expect(room.designCount).toBe(3);
  });

  it("loses nothing when the new scan fails", async () => {
    const id = roomBeingMeasured();
    const before = useRooms.getState().rooms[0];
    mockApi.current = fakeApi(failedJob);
    const failed: string[] = [];
    roomGeneration()!.watch(
      id,
      () => {},
      (reason) => failed.push(reason),
    );
    await jest.advanceTimersByTimeAsync(0);
    expect(failed).toEqual(["no_walls"]);
    expect(useRoomData.getState().content[id]).toBe(old);
    expect(useRooms.getState().rooms[0]).toEqual({ ...before, remeasure: undefined });
  });

  it("finishes a re-measure on opening the room when the new scan is done meanwhile", async () => {
    const id = roomBeingMeasured();
    mockApi.current = fakeApi(ready);
    await loadRoomContent(id);
    expect(useRooms.getState().rooms[0]?.captureId).toBe("new-capture");
    expect(useRoomData.getState().content[id]?.looks[0]?.design.id).toBe("new-best_value");
  });

  it("drops a failed re-measure on opening the room, keeping the old content", async () => {
    const id = roomBeingMeasured();
    mockApi.current = fakeApi(failedJob);
    await loadRoomContent(id);
    expect(useRooms.getState().rooms[0]?.remeasure).toBeUndefined();
    expect(useRooms.getState().rooms[0]?.captureId).toBe("old-capture");
    expect(useRoomData.getState().content[id]).toBe(old);
  });
});

describe("a room's job, followed whichever screen is open", () => {
  function newRoom() {
    useRooms.setState({ rooms: [] });
    useRoomData.setState({ content: {} });
    useRoomJobs.setState({ jobs: {} });
    const room = useRooms.getState().addRoomForCapture("job-capture", 0);
    useCaptureStore.setState({
      last: { captureId: "job-capture" } as never,
      upload: { state: "uploading", finished: 0, total: 2 },
    });
    useTaste.setState({
      answers: {
        budget: { limit: { currency: "INR", amount_minor: 100 }, flexibility: "strict" },
        must_haves: [],
        consider_vastu: false,
      } as unknown as TasteAnswers,
    });
    return room.id;
  }

  it("goes uploading, reading your room, designing, done", async () => {
    const id = newRoom();
    mockApi.current = fakeApi(ready, { id: "req", status: "working", stages: [] });
    startRoomJob(id);
    await jest.advanceTimersByTimeAsync(0);
    expect(useRoomJobs.getState().jobs[id]).toEqual({ stage: "uploading", finished: 0 });
    useCaptureStore.setState({ upload: { state: "done", finished: 2, total: 2 } });
    await jest.advanceTimersByTimeAsync(0);
    expect(useRoomJobs.getState().jobs[id]).toEqual({ stage: "designing", finished: 2 });
    (mockApi.current.getDesigns as jest.Mock).mockResolvedValue(designsReady);
    await jest.advanceTimersByTimeAsync(POLL_MS);
    expect(useRoomJobs.getState().jobs[id]).toEqual({ stage: "done", finished: 3 });
    expect(useRoomData.getState().content[id]?.looks).toHaveLength(3);
  });

  it("stops with the real reason, and Retry starts it again", async () => {
    const id = newRoom();
    useCaptureStore.setState({ upload: { state: "done", finished: 2, total: 2 } });
    mockApi.current = fakeApi(failedJob);
    startRoomJob(id);
    await jest.advanceTimersByTimeAsync(0);
    expect(useRoomJobs.getState().jobs[id]).toMatchObject({ stage: "failed", reason: "no_walls" });
    mockApi.current = fakeApi(ready);
    await retryRoomJob(id);
    await jest.advanceTimersByTimeAsync(0);
    expect(useRoomJobs.getState().jobs[id]?.stage).toBe("done");
  });

  it("the stages screen shows the job, which goes on after the screen closes", async () => {
    const id = newRoom();
    useCaptureStore.setState({ upload: { state: "done", finished: 2, total: 2 } });
    mockApi.current = fakeApi(ready, { id: "req", status: "working", stages: [] });
    const seen: number[] = [];
    const stop = roomGeneration()!.watch(id, (count) => seen.push(count));
    await jest.advanceTimersByTimeAsync(0);
    stop();
    (mockApi.current.getDesigns as jest.Mock).mockResolvedValue(designsReady);
    await jest.advanceTimersByTimeAsync(POLL_MS);
    expect(seen.at(-1)).toBe(2);
    expect(useRoomJobs.getState().jobs[id]?.stage).toBe("done");
  });
});
