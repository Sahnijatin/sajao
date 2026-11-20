// Rooms on My home. Pure: what a room is, how the list is ordered and what
// each card says. Rooms live on this phone until the API serves them; the
// store in state/rooms.ts is the only place that knows that.
import type { TasteAnswers } from "@/taste/taste-session";
import type { DesignIds } from "./designs-api";

/**
 * A still of a room. `image` is a real picture (a hero view from the twin,
 * or a render). `placeholder` is a drawn stand-in used until one exists.
 */
export type RoomStill =
  | { kind: "image"; uri: string }
  | {
      kind: "placeholder";
      look: "before" | "after";
      /** Which of three views of the drawn room; 0 when left out. */
      view?: 0 | 1 | 2;
    };

/** A photo of the room on this phone, with the id of the keyframe it was uploaded as. */
export interface RoomPhoto {
  id: string;
  uri: string;
  /** The photo's size, when it was taken in the app; used to add to the same room. */
  widthPx?: number;
  heightPx?: number;
}

export interface Room {
  id: string;
  /** The name you gave it; null shows "Room 2" from its number. */
  name: string | null;
  /** 1 for the first room added on this phone, then 2, and so on. */
  number: number;
  updatedAtMs: number;
  designCount: number;
  still: RoomStill;
  /** The scan this room came from. */
  captureId: string | null;
  /** For a scan of several areas: the one chosen to redesign. Unset until chosen. */
  redesignAreaId?: string | null;
  /** The photos the room was added with, on this phone, in order, by keyframe id. Unset for an AR scan. */
  photos?: RoomPhoto[];
  /**
   * A new scan measuring this room again, until it has been measured and its
   * designs have arrived. Until then the room keeps its capture, content and
   * designs; if the new scan fails, this is dropped and nothing is lost.
   */
  remeasure?: {
    captureId: string;
    designIds?: DesignIds;
    /** The photos of the new capture, which become the room's once it is done. */
    photos?: RoomPhoto[];
  };
  /** The budget for this room's designs. Unset until it is asked. */
  budget?: TasteAnswers["budget"];
  /** The ids its designs are asked for with, made once. Unset until designs are first asked for. */
  designIds?: DesignIds;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** Most recently updated first. */
export function sortRooms(rooms: readonly Room[]): Room[] {
  return [...rooms].sort((a, b) => b.updatedAtMs - a.updatedAtMs || b.number - a.number);
}

/** The number for the next room: one more than the highest so far. */
export function nextRoomNumber(rooms: readonly Room[]): number {
  return rooms.reduce((highest, room) => Math.max(highest, room.number), 0) + 1;
}

export function newRoom(
  rooms: readonly Room[],
  input: { id: string; captureId: string | null; atMs: number },
): Room {
  return {
    id: input.id,
    name: null,
    number: nextRoomNumber(rooms),
    updatedAtMs: input.atMs,
    designCount: 0,
    still: { kind: "placeholder", look: "before" },
    captureId: input.captureId,
  };
}

/**
 * Rooms with sample designs taken off. Designs with no real picture can only
 * have come from the stand-in, so the room goes back to having none.
 */
export function clearSampleDesigns(rooms: readonly Room[]): Room[] {
  return rooms.map((room) =>
    room.still.kind === "placeholder" && room.designCount > 0
      ? { ...room, designCount: 0, still: { kind: "placeholder", look: "before" } }
      : room,
  );
}

export interface Label {
  key: string;
  values?: Record<string, number>;
}

/** "Updated today", by calendar day on this phone. A time in the future counts as today. */
export function updatedLabel(updatedAtMs: number, nowMs: number): Label {
  const startOfDay = (ms: number) => {
    const date = new Date(ms);
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  };
  const days = Math.max(0, Math.round((startOfDay(nowMs) - startOfDay(updatedAtMs)) / DAY_MS));
  if (days === 0) return { key: "rooms.updated.today" };
  if (days === 1) return { key: "rooms.updated.yesterday" };
  if (days < 30) return { key: "rooms.updated.daysAgo", values: { count: days } };
  if (days < 60) return { key: "rooms.updated.lastMonth" };
  return { key: "rooms.updated.monthsAgo", values: { count: Math.floor(days / 30) } };
}

export function designsLabel(designCount: number): Label {
  return designCount > 0
    ? { key: "rooms.designs.count", values: { count: designCount } }
    : { key: "rooms.designs.none" };
}
