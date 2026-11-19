import twinFixture from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import {
  apiGeneration,
  contentFromTwin,
  areasFromTwin,
  failureOf,
  finishedStages,
  fitCheckedOf,
  retryableOf,
  heroViewsFrom,
  isTwin,
  looksFrom,
  POLL_MS,
  type RoomApi,
  type RoomJob,
} from "./room-api";
import type { Design, SpaceTwin } from "@sajao/schemas";
import designFixture from "../../../../packages/schemas/fixtures/v1/valid/design.json";
import type { DesignsJob, DesignsRequest } from "./designs-api";
import type { RoomContent } from "./room-content";

const fixtureDesign = designFixture as unknown as Design;
const threeDesigns = (["bold", "best_value", "best_match"] as const).map((slot) => ({
  ...fixtureDesign,
  id: `design-${slot}`,
  slot,
}));
const designsJob = (
  status: string,
  designs: unknown[] | null = null,
  detail?: string,
): DesignsJob => ({
  id: "request-1",
  status,
  stages: [
    {
      stage: "design",
      status: status === "ready" ? "done" : status === "failed" ? "failed" : "running",
      detail,
    },
  ],
  designs,
});
const REQUEST = { id: "request-1" } as DesignsRequest;

const job = (measure: string, inventory: string, detail?: string): RoomJob => ({
  id: "server-room",
  status: [measure, inventory].includes("failed")
    ? "failed"
    : measure === "done" && inventory === "done"
      ? "ready"
      : "working",
  stages: [
    { stage: "measure", status: measure, detail: measure === "failed" ? detail : null },
    { stage: "inventory", status: inventory, detail: inventory === "failed" ? detail : null },
  ],
});

describe("a room's job", () => {
  it("counts the stages done, in order", () => {
    expect(finishedStages(job("queued", "queued"))).toBe(0);
    expect(finishedStages(job("running", "queued"))).toBe(0);
    expect(finishedStages(job("done", "running"))).toBe(1);
    expect(finishedStages(job("done", "done"))).toBe(2);
    // A later stage never counts before an earlier one.
    expect(finishedStages(job("running", "done"))).toBe(0);
    expect(finishedStages({ id: "r", status: "working", stages: [] })).toBe(0);
  });

  it("gives the reason code when a stage failed", () => {
    expect(failureOf(job("done", "running"))).toBeNull();
    expect(failureOf(job("failed", "queued", "no_walls"))).toBe("no_walls");
    expect(failureOf(job("done", "failed"))).toBe("unknown");
    expect(failureOf({ id: "r", status: "failed", stages: [] })).toBe("unknown");
  });
});

describe("the twin from the server", () => {
  it("is accepted when it has the parts the app reads", () => {
    expect(isTwin(twinFixture)).toBe(true);
  });

  it("is refused when it is not a twin, or a part the app reads is missing or malformed", () => {
    const twin = twinFixture as Record<string, unknown>;
    const shell = twin.shell as Record<string, unknown>;
    for (const bad of [
      null,
      "twin",
      {},
      { ...twin, shell: undefined },
      { ...twin, space_type: 3 },
      { ...twin, objects: "none" },
      { ...twin, shell: { ...shell, walls: [] } },
      { ...twin, shell: { ...shell, floor_polygon: [{ x_m: 0, y_m: 0 }] } },
      { ...twin, shell: { ...shell, ceiling_height: { value_m: "high" } } },
      { ...twin, shell: { ...shell, walls: [{ id: "w1", length: { value_m: 4 } }] } },
    ]) {
      expect(isTwin(bad)).toBe(false);
    }
  });

  it("becomes real room content: measurements, outline and kind, no samples", () => {
    const content = contentFromTwin(twinFixture as never);
    expect(content.sample).toBe(false);
    expect(content.spaceType).toBe("living_room");
    expect(content.measures?.walls).toHaveLength(3);
    expect(content.confidence).toBe("measured");
    expect(content.shell?.floor_polygon).toHaveLength(4);
    expect(content.direction?.sources).toContain("compass");
    // No photos from this phone and no designs yet: no views, no looks.
    expect(content.heroViews).toEqual([]);
    expect(content.looks).toEqual([]);
  });
});

describe("real progress for a room", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  function setup(
    jobs: (RoomJob | Error)[],
    uploadedOk = true,
    twin: unknown = twinFixture,
    designs?: { jobs: (DesignsJob | Error)[]; request?: DesignsRequest | null },
  ) {
    const calls: string[] = [];
    let next = 0;
    let nextDesigns = 0;
    const api: RoomApi = {
      createRoom: jest.fn(async (captureId: string) => {
        calls.push(`create:${captureId}`);
        return job("queued", "queued");
      }),
      getRoom: jest.fn(async (roomId: string) => {
        calls.push(`get:${roomId}`);
        const answer = jobs[Math.min(next, jobs.length - 1)] as RoomJob | Error;
        next += 1;
        if (answer instanceof Error) throw answer;
        return answer;
      }),
      getTwin: jest.fn(async () => twin),
      requestDesigns: jest.fn(async (roomId: string, request: DesignsRequest) => {
        calls.push(`ask:${roomId}:${request.id}`);
        return designsJob("working");
      }),
      getDesigns: jest.fn(async (roomId: string) => {
        calls.push(`designs:${roomId}`);
        const list = designs?.jobs ?? [];
        const answer = list[Math.min(nextDesigns, list.length - 1)] as DesignsJob | Error;
        nextDesigns += 1;
        if (answer instanceof Error) throw answer;
        return answer;
      }),
    };
    const ready: [string, RoomContent][] = [];
    const delivered: [string, readonly Design[]][] = [];
    const finished: number[] = [];
    const failed: string[] = [];
    const source = apiGeneration(api, {
      captureIdOf: (roomId) => (roomId === "room-1" ? "capture-1" : null),
      uploaded: async () => uploadedOk,
      onReady: (roomId, content) => ready.push([roomId, content]),
      ...(designs
        ? {
            designs: {
              requestFor: () => (designs.request === undefined ? REQUEST : designs.request),
              onDesigns: (roomId: string, three: readonly Design[]) =>
                delivered.push([roomId, three]),
            },
          }
        : {}),
    });
    const stop = source.watch(
      "room-1",
      (count) => finished.push(count),
      (reason) => failed.push(reason),
    );
    const tick = async (ms = POLL_MS) => {
      await jest.advanceTimersByTimeAsync(ms);
    };
    return { api, calls, ready, delivered, finished, failed, stop, tick };
  }

  it("waits for the upload, creates the room for the scan, then follows it to the end", async () => {
    const run = setup([job("running", "queued"), job("done", "running"), job("done", "done")]);
    await run.tick(0);
    expect(run.calls).toEqual(["create:capture-1", "get:server-room"]);
    expect(run.finished).toEqual([0]);
    await run.tick();
    expect(run.finished).toEqual([0, 1]);
    await run.tick();
    expect(run.finished).toEqual([0, 1, 2]);
    expect(run.ready).toHaveLength(1);
    expect(run.ready[0]?.[0]).toBe("room-1");
    expect(run.ready[0]?.[1].sample).toBe(false);
    // Done: it stops asking.
    await run.tick(POLL_MS * 5);
    expect(run.api.getRoom).toHaveBeenCalledTimes(3);
    expect(run.failed).toEqual([]);
  });

  it("stops with the server's reason when a stage fails", async () => {
    const run = setup([job("failed", "queued", "no_walls")]);
    await run.tick(0);
    expect(run.failed).toEqual(["no_walls"]);
    await run.tick(POLL_MS * 3);
    expect(run.api.getRoom).toHaveBeenCalledTimes(1);
    expect(run.ready).toEqual([]);
  });

  it("does not create a room for a scan that did not upload", async () => {
    const run = setup([job("done", "done")], false);
    await run.tick(0);
    expect(run.failed).toEqual(["upload"]);
    expect(run.api.createRoom).not.toHaveBeenCalled();
  });

  it("keeps trying through a dropped connection", async () => {
    const run = setup([new Error("offline"), new Error("offline"), job("done", "done")]);
    await run.tick(0);
    await run.tick();
    await run.tick();
    expect(run.failed).toEqual([]);
    expect(run.finished).toEqual([2]);
  });

  it("refuses a twin it cannot read rather than show it", async () => {
    const run = setup([job("done", "done")], true, { shell: {} });
    await run.tick(0);
    expect(run.failed).toEqual(["bad_twin"]);
    expect(run.ready).toEqual([]);
  });

  it("stops asking once nobody is watching", async () => {
    const run = setup([job("running", "queued")]);
    await run.tick(0);
    run.stop();
    await run.tick(POLL_MS * 4);
    expect(run.api.getRoom).toHaveBeenCalledTimes(1);
  });

  it("once measured, asks for designs and follows them to three, in slot order", async () => {
    const run = setup([job("done", "done")], true, twinFixture, {
      jobs: [designsJob("working"), designsJob("ready", threeDesigns)],
    });
    await run.tick(0);
    expect(run.ready).toHaveLength(1);
    expect(run.finished).toEqual([2]);
    expect(run.calls).toContain("ask:server-room:request-1");
    await run.tick();
    expect(run.finished).toEqual([2, 3]);
    expect(run.delivered).toHaveLength(1);
    expect(run.delivered[0]?.[1].map((design) => design.slot)).toEqual([
      "best_value",
      "best_match",
      "bold",
    ]);
    await run.tick(POLL_MS * 4);
    expect(run.api.getDesigns).toHaveBeenCalledTimes(2);
    expect(run.failed).toEqual([]);
  });

  it("stops with the reason when designs fail, and refuses designs it cannot read", async () => {
    const failing = setup([job("done", "done")], true, twinFixture, {
      jobs: [designsJob("failed", null, "no_products")],
    });
    await failing.tick(0);
    expect(failing.failed).toEqual(["no_products"]);
    const bad = setup([job("done", "done")], true, twinFixture, {
      jobs: [designsJob("ready", threeDesigns.slice(0, 2))],
    });
    await bad.tick(0);
    expect(bad.failed).toEqual(["bad_designs"]);
    expect(bad.delivered).toEqual([]);
  });

  it("finishes every stage without asking when there is nothing to ask with", async () => {
    const run = setup([job("done", "done")], true, twinFixture, { jobs: [], request: null });
    await run.tick(0);
    expect(run.finished).toEqual([3]);
    expect(run.api.requestDesigns).not.toHaveBeenCalled();
  });

  it("stops with the room's own reason when designing fails, such as nothing fits", async () => {
    const failedDesigning: RoomJob = {
      id: "server-room",
      status: "ready",
      stages: [],
      stage: "failed",
      failure: { reason: "nothing_fits", retryable: false, stage: "designing" },
    };
    const run = setup([job("done", "done"), failedDesigning], true, twinFixture, {
      jobs: [designsJob("working")],
    });
    await run.tick(0);
    expect(run.failed).toEqual(["nothing_fits"]);
    expect(run.delivered).toEqual([]);
  });

  it("keeps asking for designs through a dropped connection", async () => {
    const run = setup([job("done", "done")], true, twinFixture, {
      jobs: [new Error("offline"), designsJob("ready", threeDesigns)],
    });
    await run.tick(0);
    await run.tick();
    expect(run.failed).toEqual([]);
    expect(run.finished).toEqual([2, 3]);
  });
});

describe("the room's own photos and its looks", () => {
  it("are the person's photos, in order, and each look is shown beside the room today", () => {
    const views = heroViewsFrom([
      { id: "k1", uri: "file:///a.jpg" },
      { id: "k2", uri: "file:///b.jpg" },
    ]);
    expect(views).toEqual([
      { id: "k1", still: { kind: "image", uri: "file:///a.jpg" } },
      { id: "k2", still: { kind: "image", uri: "file:///b.jpg" } },
    ]);
    const looks = looksFrom(threeDesigns, views);
    expect(looks.map((look) => look.still)).toEqual(Array(3).fill(views[0]?.still));
    expect(looks.every((look) => look.stillIsToday)).toBe(true);
    // No photos: a plain tile, never a drawn stand-in or another room.
    expect(looksFrom(threeDesigns, [])[0]?.still).toEqual({ kind: "placeholder", look: "before" });
  });
});

describe("a scan that went through more than one area", () => {
  const twin = twinFixture as unknown as SpaceTwin;
  const square = (x0: number, x1: number) => [
    { x_m: x0, y_m: 0 },
    { x_m: x1, y_m: 0 },
    { x_m: x1, y_m: 3.4 },
    { x_m: x0, y_m: 3.4 },
  ];
  const split = {
    ...twin,
    areas: [
      {
        id: "a1",
        space_type: "living_room",
        floor_polygon: square(0, 4.2),
        floor_area_m2: 14.28,
        object_ids: ["sofa-1"],
        keyframe_ids: ["k1"],
        photo_keyframe_id: "k1",
        confidence: { level: "ar_measured", basis: "lidar" },
      },
      {
        // The dining area beyond the open side, through the doorway.
        id: "a2",
        space_type: "dining_room",
        floor_polygon: square(-2, 0),
        floor_area_m2: 6.8,
        object_ids: ["almirah-1"],
        keyframe_ids: ["k2"],
        photo_keyframe_id: "k2",
        confidence: { level: "estimated", basis: "depth_model" },
      },
    ],
  } as unknown as SpaceTwin;
  const photos = [
    { id: "k1", uri: "file:///living.jpg" },
    { id: "k2", uri: "file:///dining.jpg" },
  ];

  it("gives each area its photo, floor, walls, openings, items and level", () => {
    const [living, dining] = areasFromTwin(split, photos);
    expect(living?.photo).toEqual({ kind: "image", uri: "file:///living.jpg" });
    expect(living?.spaceType).toBe("living_room");
    expect(living?.shell?.walls.map((wall) => wall.id)).toEqual(["w1", "w2", "w3", "w4"]);
    expect(living?.measures?.bigItems.map((item) => item.id)).toEqual(["sofa-1"]);
    expect(living?.confidence).toBe("measured");
    expect(dining?.photo).toEqual({ kind: "image", uri: "file:///dining.jpg" });
    expect(dining?.heroViews.map((view) => view.id)).toEqual(["k2"]);
    expect(dining?.shell?.walls.map((wall) => wall.id)).toEqual(["w4"]);
    expect(dining?.shell?.openings.map((opening) => opening.id)).toEqual(["d1"]);
    expect(dining?.measures?.bigItems.map((item) => item.id)).toEqual(["almirah-1"]);
    expect(dining?.confidence).toBe("estimated");
  });

  it("has no photo for an area this phone has no picture of, and no areas for one space", () => {
    expect(areasFromTwin(split, [])[0]?.photo).toBeNull();
    expect(areasFromTwin(twin, photos)).toEqual([]);
    expect(areasFromTwin({ ...twin, areas: undefined } as SpaceTwin)).toEqual([]);
  });

  it("makes the room's content carry its areas and the photos as its views", () => {
    const content = contentFromTwin(split, photos);
    expect(content.areas.map((area) => area.id)).toEqual(["a1", "a2"]);
    expect(content.heroViews.map((view) => view.id)).toEqual(["k1", "k2"]);
  });
});

describe("the room's status from a server that sends stage and failure", () => {
  const status = (stage: string, failure: RoomJob["failure"] = null): RoomJob => ({
    id: "server-room",
    status: "working",
    stages: [],
    stage,
    failure,
  });

  it("counts the room read from designing on, whatever the older rows say", () => {
    expect(finishedStages(status("uploaded"))).toBe(0);
    expect(finishedStages(status("reading"))).toBe(0);
    for (const stage of ["designing", "rendering", "ready"]) {
      expect(finishedStages(status(stage))).toBe(2);
    }
    const failedDesigning = { reason: "nothing_fits", retryable: false, stage: "designing" };
    expect(finishedStages(status("failed", failedDesigning))).toBe(2);
    expect(finishedStages(status("failed", { ...failedDesigning, stage: "reading" }))).toBe(0);
  });

  it("gives the failure's reason and whether asking again may help", () => {
    const failure = { reason: "nothing_fits", retryable: false, stage: "designing" };
    expect(failureOf(status("failed", failure))).toBe("nothing_fits");
    expect(retryableOf(status("failed", failure))).toBe(false);
    expect(failureOf(status("designing"))).toBeNull();
    expect(failureOf(status("failed"))).toBe("internal");
    expect(retryableOf(status("reading"))).toBe(true);
  });

  it("lists the items whose fit was checked; none when the server does not say", () => {
    const withItems: RoomJob = {
      ...status("ready"),
      items: [
        { design_id: "d1", item_id: "sofa", fit_checked: true },
        { design_id: "d1", item_id: "lamp", fit_checked: false },
      ],
    };
    expect(fitCheckedOf(withItems)).toEqual(["d1:sofa"]);
    expect(fitCheckedOf(status("ready"))).toBeNull();
  });
});
