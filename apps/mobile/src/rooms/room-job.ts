// The room made from an uploaded scan and the state of its job on the
// server. Creating the room is safe to repeat: the server keeps one room per
// capture and starts its pipeline again only where it stopped.
//
// The network is passed in, so this is tested without a phone.

export interface RoomStage {
  stage: string;
  /** queued, running, done or failed. */
  status: string;
  /** A short reason code when the stage failed, such as no_walls. */
  detail?: string | null;
}

export interface RoomJob {
  id: string;
  /** working, ready or failed. */
  status: string;
  stages: RoomStage[];
}

export interface RoomsApi {
  create(captureId: string): Promise<RoomJob>;
  read(roomId: string): Promise<RoomJob>;
}

const stageOf = (room: RoomJob, name: string) => room.stages.find((s) => s.stage === name);

/** True once the room's measurements are in, or the job cannot go on. */
export function isSettled(room: RoomJob): boolean {
  if (room.status !== "working") return true;
  return stageOf(room, "measure")?.status === "done";
}

export interface FollowOptions {
  onUpdate(room: RoomJob): void;
  sleep(ms: number): Promise<void>;
  now(): number;
  intervalMs?: number;
  /** Stop asking after this long; the room carries on at the server. */
  giveUpAfterMs?: number;
}

/** Create the room for a capture and follow it until it is measured, failed or slow. */
export async function followRoom(
  api: RoomsApi,
  captureId: string,
  { onUpdate, sleep, now, intervalMs = 2000, giveUpAfterMs = 120_000 }: FollowOptions,
): Promise<RoomJob> {
  const started = now();
  let room = await api.create(captureId);
  onUpdate(room);
  while (!isSettled(room) && now() - started < giveUpAfterMs) {
    await sleep(intervalMs);
    room = await api.read(room.id);
    onUpdate(room);
  }
  return room;
}

// Reasons the app has its own words for; anything else gets the general text.
const KNOWN_REASONS = new Set(["no_walls", "no_ar_data"]);

/** The message key for a room's job. */
export function roomMessage(room: RoomJob): string {
  const failed = room.stages.find((s) => s.status === "failed");
  if (failed || room.status === "failed") {
    const reason = failed?.detail ?? "";
    return KNOWN_REASONS.has(reason) ? `home.room.failed.${reason}` : "home.room.failed.other";
  }
  return isSettled(room) ? "home.room.measured" : "home.room.measuring";
}
