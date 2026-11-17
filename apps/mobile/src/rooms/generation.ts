// Progress while a room is being worked on, in three plain-word stages. The
// screen reads a `GenerationSource`; the pipeline will be one. Until it
// reports progress, a timed stand-in walks through the stages.
import { useEffect, useState } from "react";

export const GENERATION_STAGES = ["walls", "furniture", "looks"] as const;
export type GenerationStage = (typeof GENERATION_STAGES)[number];

/** The stages for a room: a space that gets no designs stops after its furniture is found. */
export function stagesFor(designs: boolean): readonly GenerationStage[] {
  return designs ? GENERATION_STAGES : GENERATION_STAGES.slice(0, 2);
}

export interface GenerationSource {
  /**
   * Calls back with the number of stages finished, 0 to 3, each time it
   * grows. Returns a function that stops watching.
   */
  watch(roomId: string, onFinished: (finished: number) => void): () => void;
}

/** How long the stand-in spends on each stage. */
export const SAMPLE_STAGE_MS = 2600;

export function timedGeneration(
  stageMs: number = SAMPLE_STAGE_MS,
  stages: number = GENERATION_STAGES.length,
): GenerationSource {
  return {
    watch(_roomId, onFinished) {
      let finished = 0;
      const timer = setInterval(() => {
        finished += 1;
        onFinished(finished);
        if (finished >= stages) clearInterval(timer);
      }, stageMs);
      return () => clearInterval(timer);
    },
  };
}

const SAMPLE_SOURCE = timedGeneration();

export interface GenerationProgress {
  /** Stages finished, 0 to 3. */
  finished: number;
  /** The stage being worked on; null once all are finished. */
  current: GenerationStage | null;
  done: boolean;
}

export function progressOf(
  finished: number,
  stages: readonly GenerationStage[] = GENERATION_STAGES,
): GenerationProgress {
  const count = Math.min(stages.length, Math.max(0, Math.floor(finished)));
  return { finished: count, current: stages[count] ?? null, done: count >= stages.length };
}

export function useGeneration(
  roomId: string,
  source: GenerationSource = SAMPLE_SOURCE,
  stages: readonly GenerationStage[] = GENERATION_STAGES,
): GenerationProgress {
  const [finished, setFinished] = useState(0);
  useEffect(() => {
    setFinished(0);
    // Progress only ever moves forward, whatever order reports arrive in.
    return source.watch(roomId, (count) => setFinished((before) => Math.max(before, count)));
  }, [roomId, source]);
  return progressOf(finished, stages);
}
