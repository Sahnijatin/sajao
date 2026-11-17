// The room API as the app uses it: create the room for a scan, follow its
// job stage by stage, and read its twin. The mapping from the API's answers
// to what screens show is pure and lives here; the network client that
// implements `RoomApi` is in room-client.ts.
import type { SpaceTwin } from "@sajao/schemas";
import type { GenerationSource } from "./generation";
import { measuresFromTwin } from "./measures";
import type { RoomContent } from "./room-content";
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
  };
}

export interface ApiGenerationOptions {
  /** The scan the room was made from. */
  captureIdOf(roomId: string): string | null;
  /** Resolves true once the scan is uploaded and registered, false if the upload failed. */
  uploaded(captureId: string): Promise<boolean>;
  /** Called with the room's content once its twin is read. */
  onReady(roomId: string, content: RoomContent): void;
  /** Milliseconds between looks at the job. */
  pollMs?: number;
}

/** How often the app asks how the room is getting on. */
export const POLL_MS = 3000;

/**
 * Real progress for a room: waits for the upload, creates the room, then
 * follows its stages until they are done or one fails.
 */
export function apiGeneration(api: RoomApi, options: ApiGenerationOptions): GenerationSource {
  const pollMs = options.pollMs ?? POLL_MS;
  return {
    watch(roomId, onFinished, onFailed) {
      let stopped = false;
      let timer: ReturnType<typeof setTimeout> | null = null;
      const fail = (reason: string) => {
        if (!stopped) onFailed?.(reason);
        stopped = true;
      };
      const follow = async (serverId: string) => {
        if (stopped) return;
        try {
          const job = await api.getRoom(serverId);
          if (stopped) return;
          const reason = failureOf(job);
          if (reason) return fail(reason);
          const finished = finishedStages(job);
          if (finished >= ROOM_STAGES.length) {
            const twin = await api.getTwin(serverId);
            if (stopped) return;
            if (!isTwin(twin)) return fail("bad_twin");
            options.onReady(roomId, contentFromTwin(twin));
          }
          onFinished(finished);
          if (finished < ROOM_STAGES.length)
            timer = setTimeout(() => void follow(serverId), pollMs);
        } catch {
          // A dropped connection is not a failed room: look again shortly.
          if (!stopped) timer = setTimeout(() => void follow(serverId), pollMs);
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
