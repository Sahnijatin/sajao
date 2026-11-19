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
  /** The camera, for the next photo, or to take one of the kept ones again. */
  | { step: "camera"; replacing?: number }
  /** The photo just taken, to keep or take again. */
  | { step: "review"; photo: TakenPhoto; replacing?: number }
  /** Every photo kept, each with its own Retake, before they are used. */
  | { step: "photos" }
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
  /** Keep the photo under review and look at all of them. */
  | { type: "continue" }
  /** From all the photos: take this one again. */
  | { type: "retakeAt"; index: number }
  /** From all the photos: take one more. */
  | { type: "addAnother" }
  /** From all the photos: use them. */
  | { type: "finish" };

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

/** Whether "Add another view" is offered on the photos: up to three in all. */
export function canAddAnother(session: PhotoSession): boolean {
  return session.current.step === "photos" && session.kept.length < MAX_PHOTOS;
}

export function photoSession(session: PhotoSession, action: PhotoAction): PhotoSession {
  const { current, kept } = session;
  switch (action.type) {
    case "start":
      return current.step === "note" ? { ...session, current: { step: "camera" } } : session;
    case "taken":
      // Only a sideways photo is ever reviewed; anything else is ignored.
      if (current.step !== "camera" || !isLandscape(action.photo)) return session;
      return {
        ...session,
        current: { step: "review", photo: action.photo, replacing: current.replacing },
      };
    case "retake":
      return current.step === "review"
        ? { ...session, current: { step: "camera", replacing: current.replacing } }
        : session;
    case "continue": {
      if (current.step !== "review") return session;
      const at = current.replacing;
      const next =
        at === undefined
          ? [...kept, current.photo]
          : kept.map((photo, index) => (index === at ? current.photo : photo));
      return { current: { step: "photos" }, kept: next };
    }
    case "retakeAt":
      if (current.step !== "photos" || action.index < 0 || action.index >= kept.length) {
        return session;
      }
      return { ...session, current: { step: "camera", replacing: action.index } };
    case "addAnother":
      return canAddAnother(session) ? { ...session, current: { step: "camera" } } : session;
    case "finish":
      return current.step === "photos" && kept.length > 0
        ? { ...session, current: { step: "done" } }
        : session;
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
