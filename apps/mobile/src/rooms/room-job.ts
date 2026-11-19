// The room made from an uploaded capture and the state of its job on the
// server. Creating the room is safe to repeat: the server keeps one room per
// capture and starts its pipeline again only where it stopped. The room's
// job (room-source.ts) is the only thing that creates and follows it.

export interface RoomStage {
  stage: string;
  /** queued, running, done or failed. */
  status: string;
  /** A short reason code when the stage failed, such as no_walls. */
  detail?: string | null;
}

/** Why a room's job stopped, as the server says it (RoomStatus.failure). */
export interface RoomFailure {
  reason: string;
  /** True when asking again may succeed; false when the photos themselves must change. */
  retryable: boolean;
  stage: string;
}

export interface RoomJob {
  id: string;
  /** working, ready or failed: the room job alone, for older servers. Read `stage`. */
  status: string;
  stages: RoomStage[];
  /** uploaded, reading, designing, rendering, ready or failed (RoomStatus). */
  stage?: string;
  /** Present exactly when `stage` is failed. */
  failure?: RoomFailure | null;
  /** Every item of every design once designs exist, with whether its fit was checked. */
  items?: { design_id: string; item_id: string; fit_checked: boolean }[];
}
