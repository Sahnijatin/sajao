// The room API as the app uses it: create the room for a scan, follow its
// job stage by stage, and read its twin. The mapping from the API's answers
// to what screens show is pure and lives here; the network client that
// implements `RoomApi` is in room-client.ts.
import type { Design, SpaceTwin } from "@sajao/schemas";
import { type DesignsJob, type DesignsRequest, readDesigns } from "./designs-api";
import type { GenerationSource } from "./generation";
import { measuresFromTwin } from "./measures";
import { confidenceOf } from "./room-shape";
import { designsOffered, type HeroView, type RoomContent, type RoomLook } from "./room-content";
import type { RoomJob } from "./room-job";

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

/** How many of the room's stages are done, in order: a later one never counts before an earlier one. */
export function finishedStages(job: RoomJob): number {
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
  const failed = job.stages.find((stage) => stage.status === "failed");
  if (failed) return failed.detail ?? "unknown";
  return job.status === "failed" ? "unknown" : null;
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

/**
 * What the Room screen shows for a real room, from its twin. Hero photos and
 * designs are not here yet: the API serves no picture links, and designs are
 * asked for separately.
 */
export function contentFromTwin(twin: SpaceTwin): RoomContent {
  return {
    sample: false,
    spaceType: twin.space_type,
    heroViews: [],
    looks: [],
    measures: measuresFromTwin(twin),
    shell: twin.shell,
    direction: twin.direction ?? null,
    // The level comes from the server or not at all; a twin split into areas is not served yet.
    confidence: confidenceOf(twin),
    areas: [],
  };
}

/** The person's own photos of the room as its hero views, in the order taken. */
export function heroViewsFrom(photos: readonly string[]): HeroView[] {
  return photos.map((uri, index) => ({ id: `photo-${index + 1}`, still: { kind: "image", uri } }));
}

/**
 * The three looks from the room's designs. There is no rendered picture of a
 * look yet, so each is shown with the room as it is today, never a stand-in.
 */
export function looksFrom(designs: readonly Design[], heroViews: readonly HeroView[]): RoomLook[] {
  const today = heroViews[0]?.still ?? ({ kind: "placeholder", look: "before" } as const);
  return designs.map((design) => ({ design, still: today, stillIsToday: true }));
}

export interface ApiGenerationOptions {
  /** The scan the room was made from. */
  captureIdOf(roomId: string): string | null;
  /** Resolves true once the scan is uploaded and registered, false if the upload failed. */
  uploaded(captureId: string): Promise<boolean>;
  /** Called with the room's content once its twin is read. */
  onReady(roomId: string, content: RoomContent): void;
  /**
   * Designs, once the room is measured. Left out, the room stops at its
   * measurements and designs are asked for later.
   */
  designs?: {
    /** The request for this room's designs; null when there is nothing to ask with. */
    requestFor(roomId: string): DesignsRequest | null;
    /** Called with the three checked designs, in slot order. */
    onDesigns(roomId: string, designs: readonly [Design, Design, Design]): void;
  };
  /** Milliseconds between looks at the job. */
  pollMs?: number;
}

/** How often the app asks how the room is getting on. */
export const POLL_MS = 3000;

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
      const fail = (reason: string) => {
        if (!stopped) onFailed?.(reason);
        stopped = true;
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
          if (read.state === "working") return later(() => followDesigns(serverId));
          options.designs.onDesigns(roomId, read.designs);
          onFinished(roomStages + 1);
        } catch {
          // A dropped connection is not a failed request: look again shortly.
          later(() => followDesigns(serverId));
        }
      };
      const askForDesigns = async (serverId: string, twin: SpaceTwin): Promise<void> => {
        const designs = options.designs;
        if (!designs) return onFinished(roomStages);
        const request = designs.requestFor(roomId);
        // A kind of space that gets no designs yet: its last stage has nothing to do.
        if (!request || !designsOffered(twin.space_type)) return onFinished(roomStages + 1);
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
          if (reason) return fail(reason);
          const finished = finishedStages(job);
          if (finished < roomStages) {
            onFinished(finished);
            return later(() => follow(serverId));
          }
          const twin = await api.getTwin(serverId);
          if (stopped) return;
          if (!isTwin(twin)) return fail("bad_twin");
          options.onReady(roomId, contentFromTwin(twin));
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
        try {
          const job = await api.createRoom(captureId);
          await follow(job.id);
        } catch {
          fail("unknown");
        }
      })();
      return () => {
        stopped = true;
        if (timer) clearTimeout(timer);
      };
    },
  };
}
