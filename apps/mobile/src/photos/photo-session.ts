// Take photos: the main way to add a room. A short note first, then the
// camera held sideways, one to three photos, each looked at once before it
// is kept ("Happy with the view and lighting?"). Pure: the screen holds this
// state and the camera glue is in take-photo.ts.
import type { ImportedFrame } from "@/import/gallery-import";

/** One to three photos make a room. */
export const MAX_PHOTOS = 3;

export interface TakenPhoto {
  uri: string;
  widthPx: number;
  heightPx: number;
}

export type PhotoStep =
  /** What makes a good photo, before the camera opens. */
  | { step: "note" }
  /** The camera, for the next photo. */
  | { step: "camera" }
  /** The photo just taken, to keep or take again. */
  | { step: "review"; photo: TakenPhoto }
  /** Done: these photos make the room. */
  | { step: "done" };

export interface PhotoSession {
  current: PhotoStep;
  /** Photos kept so far, in the order they were taken. */
  kept: TakenPhoto[];
}

export type PhotoAction =
  | { type: "start" }
  | { type: "taken"; photo: TakenPhoto }
  | { type: "retake" }
  /** Keep the photo under review and finish. */
  | { type: "continue" }
  /** Keep the photo under review and take one more. */
  | { type: "addAnother" };

export const initialSession: PhotoSession = { current: { step: "note" }, kept: [] };

/** Width over height of at least this counts as sideways. */
const LANDSCAPE_RATIO = 1.05;

/** A photo is landscape when it is clearly wider than tall. */
export function isLandscape(photo: Pick<TakenPhoto, "widthPx" | "heightPx">): boolean {
  return photo.heightPx > 0 && photo.widthPx / photo.heightPx >= LANDSCAPE_RATIO;
}

/**
 * The phone is held sideways. `uiRotation` is what the camera library says
 * the controls must turn by to read upright: 90 or 270 degrees (either sign)
 * when the phone is on its side. Unknown counts as upright.
 */
export function heldSideways(uiRotation: number | null): boolean {
  if (uiRotation === null || !Number.isFinite(uiRotation)) return false;
  return Math.abs(Math.round(uiRotation) % 180) === 90;
}

/** Whether "Add another view" is offered while reviewing: the one under review counts. */
export function canAddAnother(session: PhotoSession): boolean {
  return session.current.step === "review" && session.kept.length + 1 < MAX_PHOTOS;
}

export function photoSession(session: PhotoSession, action: PhotoAction): PhotoSession {
  const { current, kept } = session;
  switch (action.type) {
    case "start":
      return current.step === "note" ? { ...session, current: { step: "camera" } } : session;
    case "taken":
      // Only a sideways photo is ever reviewed; anything else is ignored.
      if (current.step !== "camera" || !isLandscape(action.photo)) return session;
      return { ...session, current: { step: "review", photo: action.photo } };
    case "retake":
      return current.step === "review" ? { ...session, current: { step: "camera" } } : session;
    case "continue":
      if (current.step !== "review") return session;
      return { current: { step: "done" }, kept: [...kept, current.photo] };
    case "addAnother":
      if (!canAddAnother(session) || current.step !== "review") return session;
      return { current: { step: "camera" }, kept: [...kept, current.photo] };
  }
}

/** The kept photos as frames for the capture, a second apart so their order is kept. */
export function keptFrames(kept: readonly TakenPhoto[]): ImportedFrame[] {
  return kept.map((photo, index) => ({
    uri: photo.uri,
    atMs: index * 1000,
    widthPx: photo.widthPx,
    heightPx: photo.heightPx,
  }));
}
