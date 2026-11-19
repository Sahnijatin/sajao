// Designs from the room and design API: the brief the app sends, the design
// request's job, and the three Designs once it is ready. Pure: the network
// client is in room-client.ts and the following is in room-api.ts.
import type { Brief, Design } from "@sajao/schemas";
import type { TasteAnswers } from "@/taste/taste-session";
import type { RoomStage } from "./room-job";

/** The design request's job, as the server sends it. */
export interface DesignsJob {
  id: string;
  /** working, ready or failed. */
  status: string;
  stages: RoomStage[];
  /** The three Designs once the job is ready; not yet checked. */
  designs?: unknown[] | null;
}

/**
 * The ids a room's design request is sent with, made on this phone once per
 * room and kept, so asking again is the same request. The server has no
 * endpoints for space and taste profiles yet: their ids are made here too,
 * and the engine only carries them into each Design.
 */
export interface DesignIds {
  requestId: string;
  briefId: string;
  spaceProfileId: string;
  tasteProfileId: string;
  /** When the brief was first made: a repeat sends the same brief. */
  createdAt: string;
}

export interface DesignsRequest {
  id: string;
  brief: Brief;
}

/** The request for a room's designs, from the taste and budget given on this phone. */
export function designsRequest(
  answers: TasteAnswers,
  ids: DesignIds,
  /** This room's budget; the taste answers' when the room has none. */
  budget: TasteAnswers["budget"] = answers.budget,
): DesignsRequest {
  return {
    id: ids.requestId,
    brief: {
      schema_version: "1.0",
      id: ids.briefId,
      space_profile_id: ids.spaceProfileId,
      taste_profile_id: ids.tasteProfileId,
      created_at: ids.createdAt,
      intent: "full_makeover",
      budget,
      must_haves: answers.must_haves,
      keep_item_ids: [],
      consider_vastu: answers.consider_vastu,
    },
  };
}

export const DESIGN_SLOTS = ["best_value", "best_match", "bold"] as const;

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;
const isNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

function isItem(value: unknown): boolean {
  if (!isObject(value) || typeof value.id !== "string") return false;
  const { product, position } = value;
  return (
    isObject(product) &&
    typeof product.title === "string" &&
    isObject(product.price) &&
    isNumber(product.price.amount_minor) &&
    typeof product.in_stock === "boolean" &&
    Array.isArray(product.routes) &&
    Array.isArray(product.images) &&
    isObject(product.dimensions) &&
    isObject(position) &&
    isNumber(position.x_m) &&
    isNumber(position.y_m) &&
    isNumber(value.rotation_deg)
  );
}

/**
 * Whether what the server sent has the parts of a Design the app reads. A
 * light check on the phone; the server validates the full contract and the
 * verifier has passed every design it serves.
 */
export function isDesign(value: unknown): value is Design {
  if (!isObject(value)) return false;
  return (
    typeof value.id === "string" &&
    (DESIGN_SLOTS as readonly unknown[]).includes(value.slot) &&
    Array.isArray(value.items) &&
    value.items.length > 0 &&
    value.items.every(isItem) &&
    isObject(value.total_cost) &&
    isNumber(value.total_cost.amount_minor) &&
    isObject(value.check_report) &&
    typeof value.check_report.passed === "boolean" &&
    Array.isArray(value.explanations)
  );
}

/** Why the design request failed, as the server's short reason code; null while it has not. */
export function designsFailure(job: DesignsJob): string | null {
  const failed = job.stages.find((stage) => stage.status === "failed");
  if (failed) return failed.detail ?? "unknown";
  return job.status === "failed" ? "unknown" : null;
}

export type DesignsRead =
  | { state: "working" }
  | { state: "failed"; reason: string }
  | { state: "ready"; designs: readonly [Design, Design, Design] };

/**
 * Where the design request stands. Ready means exactly one design per slot,
 * each with the parts the app reads, in slot order; anything else that calls
 * itself ready is refused rather than shown.
 */
export function readDesigns(job: DesignsJob): DesignsRead {
  const reason = designsFailure(job);
  if (reason) return { state: "failed", reason };
  if (job.status !== "ready") return { state: "working" };
  const designs = job.designs ?? [];
  if (designs.length !== DESIGN_SLOTS.length || !designs.every(isDesign)) {
    return { state: "failed", reason: "bad_designs" };
  }
  const bySlot = DESIGN_SLOTS.map((slot) => designs.find((design) => design.slot === slot));
  if (bySlot.some((design) => design === undefined)) {
    return { state: "failed", reason: "bad_designs" };
  }
  return { state: "ready", designs: bySlot as [Design, Design, Design] };
}
