// The room API as the app uses it: create the room for a scan, follow its
// job stage by stage, and read its twin. The mapping from the API's answers
// to what screens show is pure and lives here; the network client that
// implements `RoomApi` is in room-client.ts.
import type { Design, SpaceTwin } from "@sajao/schemas";
import { type DesignsJob, type DesignsRequest, readDesigns } from "./designs-api";
import type { GenerationSource } from "./generation";
import { measuresFromTwin } from "./measures";
import { confidenceOf, EDGE_TOLERANCE_M } from "./room-shape";
import {
  designsOffered,
  type HeroView,
  type RoomArea,
  type RoomContent,
  type RoomLook,
} from "./room-content";
import type { RoomJob } from "./room-job";
import type { RoomPhoto } from "./rooms";

// The room's job is the capture session's type: the upload makes the room
// and follows its measuring; this follows it to the end and reads its twin.
export type { RoomJob } from "./room-job";

export interface RoomApi {
  /** Creates the room for a registered capture and starts measuring it. Safe to repeat. */
  createRoom(captureId: string): Promise<RoomJob>;
  getRoom(roomId: string): Promise<RoomJob>;
  /** The room's SpaceTwin, as sent. Not yet checked. */
  getTwin(roomId: string): Promise<unknown>;
  /** Asks for the room's designs. Safe to repeat with the same request id. */
  requestDesigns(roomId: string, request: DesignsRequest): Promise<DesignsJob>;
  /** The room's latest design request and, once ready, its designs. */
  getDesigns(roomId: string): Promise<DesignsJob>;
}

/** The room's stages on the server, in the order the app counts them. */
export const ROOM_STAGES = ["measure", "inventory"] as const;

/** Stages at which the room has been read: its twin exists. */
const READ_STAGES = ["designing", "rendering", "ready"];

/** How many of the room's stages are done, in order: a later one never counts before an earlier one. */
export function finishedStages(job: RoomJob): number {
  if (job.stage) {
    const read =
      READ_STAGES.includes(job.stage) ||
      (job.stage === "failed" && READ_STAGES.includes(job.failure?.stage ?? ""));
    return read ? ROOM_STAGES.length : 0;
  }
  let finished = 0;
  for (const name of ROOM_STAGES) {
    const stage = job.stages.find((each) => each.stage === name);
    if (stage?.status !== "done") break;
    finished += 1;
  }
  return finished;
}

/** Why the job failed, as the server's short reason code; null while it has not. */
export function failureOf(job: RoomJob): string | null {
  if (job.stage) return job.stage === "failed" ? (job.failure?.reason ?? "internal") : null;
  const failed = job.stages.find((stage) => stage.status === "failed");
  if (failed) return failed.detail ?? "unknown";
  return job.status === "failed" ? "unknown" : null;
}

/** Whether asking again may help, as the server says; true when it does not say. */
export function retryableOf(job: RoomJob): boolean {
  return job.failure?.retryable ?? true;
}

/** The items whose fit the verifier checked against measured sizes, as "design:item". */
export function fitCheckedOf(job: RoomJob): string[] | null {
  if (!job.items) return null;
  return job.items
    .filter((item) => item.fit_checked)
    .map((item) => `${item.design_id}:${item.item_id}`);
}

/**
 * Whether what the server sent has the parts of a SpaceTwin the app reads.
 * A light check on the phone; the server validates the full contract.
 */
export function isTwin(data: unknown): data is SpaceTwin {
  if (typeof data !== "object" || data === null) return false;
  const twin = data as Partial<SpaceTwin>;
  const shell = twin.shell;
  const dimension = (value: unknown) =>
    typeof value === "object" &&
    value !== null &&
    typeof (value as { value_m?: unknown }).value_m === "number" &&
    typeof (value as { error_band_m?: unknown }).error_band_m === "number" &&
    typeof (value as { source?: unknown }).source === "string";
  return (
    typeof twin.space_type === "string" &&
    typeof shell === "object" &&
    shell !== null &&
    Array.isArray(shell.floor_polygon) &&
    shell.floor_polygon.length >= 3 &&
    Array.isArray(shell.walls) &&
    shell.walls.length > 0 &&
    shell.walls.every((wall) => dimension(wall.length)) &&
    dimension(shell.ceiling_height) &&
    Array.isArray(shell.openings) &&
    Array.isArray(twin.objects)
  );
}

type Metres = { x_m: number; y_m: number };

function distanceToSegment(p: Metres, a: Metres, b: Metres): number {
  const dx = b.x_m - a.x_m;
  const dy = b.y_m - a.y_m;
  const lengthSq = dx * dx + dy * dy;
  const t =
    lengthSq === 0
      ? 0
      : Math.max(0, Math.min(1, ((p.x_m - a.x_m) * dx + (p.y_m - a.y_m) * dy) / lengthSq));
  return Math.hypot(p.x_m - (a.x_m + t * dx), p.y_m - (a.y_m + t * dy));
}

/** Whether a point lies on the outline of a floor polygon, within the edge tolerance. */
function onOutline(point: Metres, polygon: readonly Metres[]): boolean {
  return polygon.some(
    (a, index) =>
      distanceToSegment(point, a, polygon[(index + 1) % polygon.length] as Metres) <=
      EDGE_TOLERANCE_M,
  );
}

/** The person's own photos of the room as its hero views, in the order taken. */
export function heroViewsFrom(photos: readonly RoomPhoto[]): HeroView[] {
  return photos.map((photo) => ({ id: photo.id, still: { kind: "image", uri: photo.uri } }));
}

/**
 * The room's areas, from its twin, when the scan went through more than one
 * space. Each area gets its own floor, the walls and openings along it, the
 * objects in it, its photo when this phone has it, and its own confidence.
 */
export function areasFromTwin(twin: SpaceTwin, photos: readonly RoomPhoto[] = []): RoomArea[] {
  const areas = twin.areas ?? [];
  if (areas.length < 2) return [];
  return areas.map((area) => {
    const polygon = area.floor_polygon;
    // An area can have no wall of its own on record; the plan then draws its floor alone.
    const walls = twin.shell.walls.filter(
      (wall) => onOutline(wall.start, polygon) && onOutline(wall.end, polygon),
    ) as SpaceTwin["shell"]["walls"];
    const wallIds = new Set(walls.map((wall) => wall.id));
    const shell = {
      ...twin.shell,
      floor_polygon: polygon,
      walls,
      openings: twin.shell.openings.filter((opening) => wallIds.has(opening.wall_id)),
    };
    const inArea = new Set(area.object_ids);
    const areaTwin = {
      ...twin,
      shell,
      objects: twin.objects.filter((object) => inArea.has(object.id)),
    };
    const photo = photos.find((each) => each.id === area.photo_keyframe_id);
    const own = photos.filter((each) => area.keyframe_ids.includes(each.id));
    return {
      id: area.id,
      spaceType: area.space_type ?? null,
      photo: photo ? { kind: "image", uri: photo.uri } : null,
      heroViews: heroViewsFrom(own),
      measures: measuresFromTwin(areaTwin),
      shell,
      // An area's own level when the twin gives one, else the room's.
      confidence: confidenceOf(area.confidence ? area : twin),
    };
  });
}

/**
 * The three looks from the room's designs. There is no rendered picture of a
 * look yet, so each is shown with the room as it is today, never a stand-in.
 */
export function looksFrom(designs: readonly Design[], heroViews: readonly HeroView[]): RoomLook[] {
  const today = heroViews[0]?.still ?? ({ kind: "placeholder", look: "before" } as const);
  return designs.map((design) => ({ design, still: today, stillIsToday: true }));
}

/**
 * What the Room screen shows for a real room, from its twin and the photos
 * this phone took of it. Designs are asked for separately.
 */
export function contentFromTwin(twin: SpaceTwin, photos: readonly RoomPhoto[] = []): RoomContent {
  return {
    sample: false,
    spaceType: twin.space_type,
    heroViews: heroViewsFrom(photos),
    looks: [],
    measures: measuresFromTwin(twin),
    shell: twin.shell,
    direction: twin.direction ?? null,
    // The level comes from the server or not at all.
    confidence: confidenceOf(twin),
    areas: areasFromTwin(twin, photos),
  };
}

export interface ApiGenerationOptions {
  /** The scan the room was made from. */
  captureIdOf(roomId: string): string | null;
  /** Resolves true once the scan is uploaded and registered, false if the upload failed. */
  uploaded(captureId: string): Promise<boolean>;
  /** Called with the room's content once its twin is read. */
  onReady(roomId: string, content: RoomContent): void;
  /** The photos this phone took of the room, to show as the room and its areas. */
  photosOf?(roomId: string): readonly RoomPhoto[];
  /**
   * Designs, once the room is measured. Left out, the room stops at its
   * measurements and designs are asked for later.
   */
  designs?: {
    /** The request for this room's designs; null when there is nothing to ask with. */
    requestFor(roomId: string): DesignsRequest | null;
    /**
     * Called with the three checked designs, in slot order, and the items
     * whose fit was checked ("design:item"); null when the server does not say.
     */
    onDesigns(
      roomId: string,
      designs: readonly [Design, Design, Design],
      fitChecked: string[] | null,
    ): void;
  };
  /** Called once the photos or scan are uploaded, before the room is created. */
  onUploaded?(roomId: string): void;
  /** Called once every stage is done, after the designs (if any) were delivered. */
  onSettled?(roomId: string): void;
  /** Called when a stage fails, with the reason and whether asking again may help. */
  onFailed?(roomId: string, reason: string, retryable: boolean): void;
  /** Milliseconds between looks at the job. */
  pollMs?: number;
}

/** How often the app asks how the room is getting on. */
export const POLL_MS = 3000;

/** Tries at creating the room before it counts as failed. */
export const CREATE_ATTEMPTS = 5;

/**
 * Real progress for a room: waits for the upload, creates the room, follows
 * its stages until it is measured, then, when designs are wanted, asks for
 * them and follows that request to its three designs. Stops at the first
 * stage that fails, with the server's reason.
 */
export function apiGeneration(api: RoomApi, options: ApiGenerationOptions): GenerationSource {
  const pollMs = options.pollMs ?? POLL_MS;
  const roomStages = ROOM_STAGES.length;
  return {
    watch(roomId, onFinished, onFailed) {
      let stopped = false;
      let timer: ReturnType<typeof setTimeout> | null = null;
      const fail = (reason: string, retryable = true) => {
        if (!stopped) {
          options.onFailed?.(roomId, reason, retryable);
          onFailed?.(reason);
        }
        stopped = true;
      };
      const settle = (finished: number) => {
        options.onSettled?.(roomId);
        onFinished(finished);
      };
      const later = (next: () => Promise<void>) => {
        if (!stopped) timer = setTimeout(() => void next(), pollMs);
      };
      const followDesigns = async (serverId: string): Promise<void> => {
        if (stopped || !options.designs) return;
        try {
          const read = readDesigns(await api.getDesigns(serverId));
          if (stopped) return;
          if (read.state === "failed") return fail(read.reason);
          // The room's status says why designing stopped (such as nothing_fits).
          const room = await api.getRoom(serverId);
          if (stopped) return;
          const reason = failureOf(room);
          if (reason) return fail(reason, retryableOf(room));
          if (read.state === "working") return later(() => followDesigns(serverId));
          options.designs.onDesigns(roomId, read.designs, fitCheckedOf(room));
          settle(roomStages + 1);
        } catch {
          // A dropped connection is not a failed request: look again shortly.
          later(() => followDesigns(serverId));
        }
      };
      const askForDesigns = async (serverId: string, twin: SpaceTwin): Promise<void> => {
        const designs = options.designs;
        if (!designs) return settle(roomStages);
        const request = designs.requestFor(roomId);
        // A kind of space that gets no designs yet: its last stage has nothing to do.
        if (!request || !designsOffered(twin.space_type)) return settle(roomStages + 1);
        onFinished(roomStages);
        try {
          const job = await api.requestDesigns(serverId, request);
          if (stopped) return;
          const reason = readDesigns(job);
          if (reason.state === "failed") return fail(reason.reason);
        } catch {
          // Asking again is the same request, so the next look asks once more.
          return later(() => askForDesigns(serverId, twin));
        }
        await followDesigns(serverId);
      };
      const follow = async (serverId: string): Promise<void> => {
        if (stopped) return;
        try {
          const job = await api.getRoom(serverId);
          if (stopped) return;
          const reason = failureOf(job);
          if (reason) return fail(reason, retryableOf(job));
          const finished = finishedStages(job);
          if (finished < roomStages) {
            onFinished(finished);
            return later(() => follow(serverId));
          }
          const twin = await api.getTwin(serverId);
          if (stopped) return;
          if (!isTwin(twin)) return fail("bad_twin");
          options.onReady(roomId, contentFromTwin(twin, options.photosOf?.(roomId) ?? []));
          await askForDesigns(serverId, twin);
        } catch {
          // A dropped connection is not a failed room: look again shortly.
          later(() => follow(serverId));
        }
      };
      void (async () => {
        const captureId = options.captureIdOf(roomId);
        if (!captureId) return fail("unknown");
        if (!(await options.uploaded(captureId))) return fail("upload");
        if (stopped) return;
        options.onUploaded?.(roomId);
        // Creating the room can meet a busy or dropped request (the API answers
        // 409 while the same idempotent request is still running): ask again,
        // a few times, before calling the room failed.
        for (let attempt = 1; ; attempt += 1) {
          try {
            const job = await api.createRoom(captureId);
            if (stopped) return;
            return await follow(job.id);
          } catch {
            if (stopped) return;
            if (attempt >= CREATE_ATTEMPTS) return fail("unknown");
            await new Promise<void>((resolve) => {
              timer = setTimeout(resolve, pollMs);
            });
            if (stopped) return;
          }
        }
      })();
      return () => {
        stopped = true;
        if (timer) clearTimeout(timer);
      };
    },
  };
}
