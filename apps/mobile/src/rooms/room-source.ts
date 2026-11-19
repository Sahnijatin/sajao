// Where a room's progress and content come from in this build: the room API
// when a server is configured, the timed stand-in where samples are allowed,
// and nothing otherwise.
import { useCaptureStore } from "@/state/capture";
import { useRoomData } from "@/state/room-data";
import { useRooms } from "@/state/rooms";
import type { GenerationSource } from "./generation";
import { uuidV4 } from "@/capture/package/upload-capture";
import { useTaste } from "@/state/taste";
import { designsRequest, readDesigns } from "./designs-api";
import {
  apiGeneration,
  contentFromTwin,
  failureOf,
  isTwin,
  looksFrom,
  type RoomApi,
} from "./room-api";
import { roomApi } from "./room-client";

let api: RoomApi | null | undefined;
/** The room API for this build, made once; null when no server is configured. */
export function configuredRoomApi(): RoomApi | null {
  if (api === undefined) api = roomApi();
  return api;
}

const roomOf = (roomId: string) => useRooms.getState().rooms.find((room) => room.id === roomId);
const captureIdOf = (roomId: string) => roomOf(roomId)?.captureId ?? null;

/** The photos this phone took of a room; none for an AR scan. */
const photosOf = (roomId: string) => roomOf(roomId)?.photos ?? [];

/** Resolves once the last scan's upload has finished: true when it is up, false when it failed. */
function uploaded(captureId: string): Promise<boolean> {
  return new Promise((resolve) => {
    const settle = () => {
      const { upload, last } = useCaptureStore.getState();
      // A different scan is the latest one: this one's upload is long over.
      if (last && last.captureId !== captureId) return (resolve(true), true);
      if (upload.state === "done") return (resolve(true), true);
      if (upload.state === "failed" || upload.state === "waiting") return (resolve(false), true);
      return false;
    };
    if (settle()) return;
    const stop = useCaptureStore.subscribe(() => {
      if (settle()) stop();
    });
  });
}

/** Real progress for a room, or null when this build has no server. */
export function roomGeneration(): GenerationSource | null {
  const client = configuredRoomApi();
  if (!client) return null;
  return apiGeneration(client, {
    captureIdOf,
    uploaded,
    photosOf,
    onReady: (roomId, content) => useRoomData.getState().setContent(roomId, content),
    designs: {
      requestFor(roomId) {
        const answers = useTaste.getState().answers;
        const ids = useRooms.getState().designIdsFor(roomId, uuidV4);
        return answers && ids ? designsRequest(answers, ids, roomOf(roomId)?.budget) : null;
      },
      onDesigns(roomId, designs) {
        const content = useRoomData.getState().content[roomId];
        if (!content) return;
        const looks = looksFrom(designs, content.heroViews);
        useRoomData.getState().setContent(roomId, { ...content, looks });
        // The room's card on My home now shows its designs.
        const still = looks[0]?.still;
        if (still) useRooms.getState().setRoomDesigns(roomId, looks.length, still);
      },
    },
  });
}

/**
 * Reads a room's content from the server when the room is opened and this
 * phone does not hold it. Quietly does nothing when there is no server, the
 * room is still being worked on, or the read fails: the screen then keeps
 * saying the room is being prepared.
 */
export async function loadRoomContent(roomId: string): Promise<void> {
  const client = configuredRoomApi();
  const captureId = captureIdOf(roomId);
  if (!client || !captureId || useRoomData.getState().content[roomId]) return;
  try {
    // Creating the room is safe to repeat and answers with its id and job.
    const job = await client.createRoom(captureId);
    if (job.status !== "ready" || failureOf(job)) return;
    const twin = await client.getTwin(job.id);
    if (!isTwin(twin)) return;
    const content = contentFromTwin(twin, photosOf(roomId));
    useRoomData.getState().setContent(roomId, content);
    // Designs, if they were asked for and are ready.
    const read = readDesigns(await client.getDesigns(job.id));
    if (read.state === "ready") {
      useRoomData
        .getState()
        .setContent(roomId, { ...content, looks: looksFrom(read.designs, content.heroViews) });
    }
  } catch {
    // Offline, or the server is busy: the next open tries again.
  }
}
