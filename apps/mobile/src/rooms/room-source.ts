// Where a room's progress and content come from in this build: the room API
// when a server is configured, the timed stand-in where samples are allowed,
// and nothing otherwise.
import { useCaptureStore } from "@/state/capture";
import { useRoomData } from "@/state/room-data";
import { type RoomJobState, useRoomJobs } from "@/state/room-jobs";
import { breadcrumb } from "@/telemetry/breadcrumbs";
import { useRooms } from "@/state/rooms";
import type { GenerationSource } from "./generation";
import { uuidV4 } from "@/capture/package/upload-capture";
import { useTaste } from "@/state/taste";
import { designsRequest, readDesigns } from "./designs-api";
import {
  apiGeneration,
  contentFromTwin,
  failureOf,
  fitCheckedOf,
  isTwin,
  looksFrom,
  ROOM_STAGES,
  type RoomApi,
} from "./room-api";
import { roomApi } from "./room-client";
import { designsOffered, type RoomContent } from "./room-content";

let api: RoomApi | null | undefined;
/** The room API for this build, made once; null when no server is configured. */
export function configuredRoomApi(): RoomApi | null {
  if (api === undefined) api = roomApi();
  return api;
}

const roomOf = (roomId: string) => useRooms.getState().rooms.find((room) => room.id === roomId);
/** The capture being worked on: the new scan while the room is measured again. */
const workingCaptureOf = (roomId: string) => {
  const room = roomOf(roomId);
  return room?.remeasure?.captureId ?? room?.captureId ?? null;
};

/**
 * A new scan's content while its room is measured again, held aside so the
 * room keeps showing what it had. Swapped in once the new scan is done.
 */
const held: Record<string, RoomContent> = {};

/** The room's content, or the held one while it is measured again. */
function showOrHold(roomId: string, content: RoomContent): void {
  if (roomOf(roomId)?.remeasure) held[roomId] = content;
  else useRoomData.getState().setContent(roomId, content);
}

/** The new scan is done: its content replaces the room's, and the room follows it. */
function finishRemeasure(roomId: string): void {
  const content = held[roomId];
  if (!roomOf(roomId)?.remeasure || !content) return;
  delete held[roomId];
  useRoomData.getState().setContent(roomId, content);
  useRooms.getState().finishRemeasure(roomId);
  showDesignsOnCard(roomId, content);
}

/** The new scan failed: it is dropped, and the room stays as it was. */
function abandonRemeasure(roomId: string): void {
  delete held[roomId];
  if (roomOf(roomId)?.remeasure) useRooms.getState().abandonRemeasure(roomId);
}

/** The room's card on My home shows its designs. */
function showDesignsOnCard(roomId: string, content: RoomContent): void {
  const still = content.looks[0]?.still;
  if (still) useRooms.getState().setRoomDesigns(roomId, content.looks.length, still);
}

/** The photos this phone took of a room; none for an AR scan. */
const photosOf = (roomId: string) => roomOf(roomId)?.photos ?? [];

/**
 * Resolves once this capture's upload has finished: true when it is up,
 * false when it failed or this build cannot upload. It reads this capture's
 * own state, never the last upload's. A capture this session never saw
 * uploaded earlier, unless it is the upload still waiting to be resumed.
 */
function uploaded(captureId: string): Promise<boolean> {
  return new Promise((resolve) => {
    const settle = (): boolean => {
      const state = useCaptureStore.getState().uploads[captureId];
      if (state === "done") return (resolve(true), true);
      if (state === "failed" || state === "waiting") return (resolve(false), true);
      return false;
    };
    if (settle()) return;
    const stop = useCaptureStore.subscribe(() => {
      if (settle()) stop();
    });
    if (useCaptureStore.getState().uploads[captureId] === undefined) {
      void import("@/capture/package/pending-upload")
        .then(({ loadPendingUpload }) => loadPendingUpload())
        .then((pending) => {
          if (pending?.local.captureId === captureId) return;
          // Not waiting to be resumed: it went up in an earlier session.
          if (useCaptureStore.getState().uploads[captureId] === undefined) {
            stop();
            resolve(true);
          }
        })
        .catch(() => undefined);
    }
  });
}

/** The source of a room's job: the API generation with this phone's hooks. */
function jobSource(
  client: RoomApi,
  hooks: {
    onUploaded: () => void;
    onSettled: () => void;
    onFailed?: (reason: string, retryable: boolean) => void;
  },
) {
  return apiGeneration(client, {
    captureIdOf: workingCaptureOf,
    uploaded,
    photosOf,
    onReady: showOrHold,
    onUploaded: hooks.onUploaded,
    onSettled: (roomId) => {
      finishRemeasure(roomId);
      hooks.onSettled();
    },
    onFailed: (roomId, reason, retryable) => {
      abandonRemeasure(roomId);
      hooks.onFailed?.(reason, retryable);
    },
    designs: {
      requestFor(roomId) {
        const answers = useTaste.getState().answers;
        const ids = useRooms.getState().designIdsFor(roomId, uuidV4);
        return answers && ids ? designsRequest(answers, ids, roomOf(roomId)?.budget) : null;
      },
      onDesigns(roomId, designs, fitChecked) {
        const holding = Boolean(roomOf(roomId)?.remeasure);
        const content = holding ? held[roomId] : useRoomData.getState().content[roomId];
        if (!content) return;
        const withLooks = {
          ...content,
          looks: looksFrom(designs, content.heroViews),
          fitChecked,
        };
        if (holding) {
          held[roomId] = withLooks;
          return;
        }
        useRoomData.getState().setContent(roomId, withLooks);
        showDesignsOnCard(roomId, withLooks);
      },
    },
  });
}

/** Rooms whose job this phone is following, and how to stop following each. */
const following: Record<string, () => void> = {};

/**
 * Follow a room's job until it is done or fails, whichever screen is open:
 * the stages, the room or none. Safe to call again: a job already followed
 * is left alone. False when this build has no server.
 */
export function startRoomJob(roomId: string): boolean {
  const client = configuredRoomApi();
  if (!client) return false;
  if (following[roomId]) return true;
  const set = (job: RoomJobState) => {
    breadcrumb("job", job.stage, {
      roomId,
      captureId: workingCaptureOf(roomId),
      finished: job.finished,
      reason: job.reason ?? null,
    });
    useRoomJobs.getState().setJob(roomId, job);
  };
  let settled = false;
  let retryable = true;
  set({ stage: "uploading", finished: 0 });
  const source = jobSource(client, {
    onUploaded: () => set({ stage: "reading", finished: 1 }),
    onSettled: () => {
      settled = true;
    },
    onFailed: (_reason, canRetry) => {
      retryable = canRetry;
    },
  });
  following[roomId] = source.watch(
    roomId,
    (finished) => {
      // Shown as three stages: uploaded, the room read, the designs made.
      if (settled) {
        set({ stage: "done", finished: 3 });
        delete following[roomId];
      } else if (finished >= ROOM_STAGES.length) {
        set({ stage: "designing", finished: 2 });
      }
    },
    (reason) => {
      const before = useRoomJobs.getState().jobs[roomId]?.finished ?? 0;
      set({ stage: "failed", finished: before, reason, retryable });
      delete following[roomId];
    },
  );
  return true;
}

/** Try a failed room again: its upload first if that is what stopped, then the job. */
export async function retryRoomJob(roomId: string): Promise<void> {
  const reason = useRoomJobs.getState().jobs[roomId]?.reason;
  following[roomId]?.();
  delete following[roomId];
  useRoomJobs.getState().clearJob(roomId);
  if (reason === "upload") {
    const { resumePendingUpload } = await import("@/capture/package/start-upload");
    void resumePendingUpload();
  }
  startRoomJob(roomId);
}

/**
 * Real progress for a room, for the stages screen, or null when this build
 * has no server. It shows the room's job, which goes on if the screen closes.
 */
export function roomGeneration(): GenerationSource | null {
  if (!configuredRoomApi()) return null;
  return {
    watch(roomId, onFinished, onFailed) {
      const job = useRoomJobs.getState().jobs[roomId];
      // A room whose job ended earlier is shown as it ended; Retry starts it again.
      if (!job || job.stage === "done") startRoomJob(roomId);
      const emit = () => {
        const now = useRoomJobs.getState().jobs[roomId];
        if (!now) return;
        onFinished(now.finished);
        if (now.stage === "failed") onFailed?.(now.reason ?? "unknown");
      };
      emit();
      return useRoomJobs.subscribe(emit);
    },
  };
}

/**
 * A room's content as the server has it for one capture: its twin, and its
 * designs when they are ready. null while the room is still being worked on;
 * "failed" when its job failed.
 */
async function readRoom(
  client: RoomApi,
  roomId: string,
  captureId: string,
): Promise<RoomContent | "failed" | null> {
  // Creating the room is safe to repeat and answers with its id and job.
  const job = await client.createRoom(captureId);
  if (failureOf(job)) return "failed";
  if (job.status !== "ready") return null;
  const twin = await client.getTwin(job.id);
  if (!isTwin(twin)) return null;
  const content = contentFromTwin(twin, photosOf(roomId));
  try {
    const read = readDesigns(await client.getDesigns(job.id));
    if (read.state === "ready") {
      const status = await client.getRoom(job.id);
      return {
        ...content,
        looks: looksFrom(read.designs, content.heroViews),
        fitChecked: fitCheckedOf(status),
      };
    }
  } catch {
    // No designs asked for yet: the room is measured, with no looks.
  }
  return content;
}

/**
 * Reads a room's content from the server when the room is opened and this
 * phone does not hold it, and checks on a scan measuring it again. Quietly
 * does nothing when there is no server, the room is still being worked on,
 * or the read fails: the screen then keeps what it shows.
 */
export async function loadRoomContent(roomId: string): Promise<void> {
  const client = configuredRoomApi();
  const room = roomOf(roomId);
  if (!client || !room) return;
  try {
    if (room.captureId && !useRoomData.getState().content[roomId]) {
      const content = await readRoom(client, roomId, room.captureId);
      if (content && content !== "failed") useRoomData.getState().setContent(roomId, content);
    }
    const pending = roomOf(roomId)?.remeasure;
    if (pending) {
      const content = await readRoom(client, roomId, pending.captureId);
      if (content === "failed") abandonRemeasure(roomId);
      // Done once its designs are in (or it is a space that gets none).
      else if (content && (content.looks.length > 0 || !designsOffered(content.spaceType))) {
        held[roomId] = content;
        finishRemeasure(roomId);
      }
    }
  } catch {
    // Offline, or the server is busy: the next open tries again.
  }
}
