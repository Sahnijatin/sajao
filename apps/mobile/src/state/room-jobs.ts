// Each room's job as this phone sees it: which stage it is at, or why it
// stopped. In memory; the job itself lives at the server and is asked again.
import { create } from "zustand";

export type JobStage = "uploading" | "reading" | "designing" | "done" | "failed";

export interface RoomJobState {
  stage: JobStage;
  /** Stages finished, 0 to 3, as the stages screen counts them. */
  finished: number;
  /** The server's short reason code, or "upload", when the job failed. */
  reason?: string;
}

interface RoomJobs {
  jobs: Record<string, RoomJobState>;
  setJob(roomId: string, job: RoomJobState): void;
  clearJob(roomId: string): void;
}

export const useRoomJobs = create<RoomJobs>((set) => ({
  jobs: {},
  setJob: (roomId, job) => set((state) => ({ jobs: { ...state.jobs, [roomId]: job } })),
  clearJob: (roomId) =>
    set((state) => {
      const { [roomId]: _gone, ...rest } = state.jobs;
      return { jobs: rest };
    }),
}));

/** Whether the job is still being worked on. */
export function jobRunning(job: RoomJobState | undefined): boolean {
  return job !== undefined && job.stage !== "done" && job.stage !== "failed";
}
