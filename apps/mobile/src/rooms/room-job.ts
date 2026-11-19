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

export interface RoomJob {
  id: string;
  /** working, ready or failed. */
  status: string;
  stages: RoomStage[];
}
