import { importedCapture } from "@/import/gallery-import";
import { registerBody } from "@/capture/package/upload-capture";
import { buildPackage } from "@/capture/package/recorder";
import {
  canAddAnother,
  heldSideways,
  initialSession,
  isLandscape,
  keptFrames,
  MAX_PHOTOS,
  type PhotoAction,
  photoSession,
  type PhotoSession,
  sessionWith,
  type TakenPhoto,
} from "./photo-session";

const wide = (n: number): TakenPhoto => ({
  uri: `file:///p${n}.jpg`,
  widthPx: 1600,
  heightPx: 1200,
});
const tall: TakenPhoto = { uri: "file:///tall.jpg", widthPx: 1200, heightPx: 1600 };

const run = (...actions: PhotoAction[]): PhotoSession =>
  actions.reduce(photoSession, initialSession);

describe("Take photos", () => {
  it("opens on the note, then the camera", () => {
    expect(initialSession.current.step).toBe("note");
    expect(run({ type: "start" }).current.step).toBe("camera");
  });

  it("reviews a sideways photo and ignores one taken upright", () => {
    expect(run({ type: "start" }, { type: "taken", photo: tall }).current.step).toBe("camera");
    const session = run({ type: "start" }, { type: "taken", photo: wide(1) });
    expect(session.current).toEqual({ step: "review", photo: wide(1) });
    expect(session.kept).toEqual([]);
  });

  it("retake drops the photo and returns to the camera", () => {
    const session = run({ type: "start" }, { type: "taken", photo: wide(1) }, { type: "retake" });
    expect(session).toEqual({ current: { step: "camera" }, kept: [] });
  });

  it("continue keeps the photo and shows all of them; use finishes", () => {
    const session = run({ type: "start" }, { type: "taken", photo: wide(1) }, { type: "continue" });
    expect(session).toEqual({ current: { step: "photos" }, kept: [wide(1)] });
    expect(photoSession(session, { type: "finish" })).toEqual({
      current: { step: "done" },
      kept: [wide(1)],
    });
  });

  it("takes at most three photos", () => {
    const three = run(
      { type: "start" },
      { type: "taken", photo: wide(1) },
      { type: "continue" },
      { type: "addAnother" },
      { type: "taken", photo: wide(2) },
      { type: "continue" },
      { type: "addAnother" },
      { type: "taken", photo: wide(3) },
      { type: "continue" },
    );
    expect(three.kept).toEqual([wide(1), wide(2), wide(3)]);
    expect(three.kept).toHaveLength(MAX_PHOTOS);
    expect(canAddAnother(three)).toBe(false);
    expect(photoSession(three, { type: "addAnother" })).toBe(three);
  });

  it("retakes any one photo in its own place", () => {
    const two = run(
      { type: "start" },
      { type: "taken", photo: wide(1) },
      { type: "continue" },
      { type: "addAnother" },
      { type: "taken", photo: wide(2) },
      { type: "continue" },
    );
    const replaced = [
      { type: "retakeAt", index: 0 },
      { type: "taken", photo: wide(9) },
      { type: "retake" },
      { type: "taken", photo: wide(8) },
      { type: "continue" },
    ].reduce((state, action) => photoSession(state, action as PhotoAction), two);
    expect(replaced).toEqual({ current: { step: "photos" }, kept: [wide(8), wide(2)] });
    expect(photoSession(two, { type: "retakeAt", index: 5 })).toBe(two);
  });

  it("ignores actions that do not fit the step", () => {
    expect(photoSession(initialSession, { type: "continue" })).toBe(initialSession);
    expect(photoSession(initialSession, { type: "taken", photo: wide(1) })).toBe(initialSession);
    const camera = run({ type: "start" });
    expect(photoSession(camera, { type: "retake" })).toBe(camera);
    expect(photoSession(camera, { type: "start" })).toBe(camera);
  });

  it("knows sideways from the device orientation and the picture", () => {
    expect(heldSideways(90)).toBe(true);
    expect(heldSideways(-90)).toBe(true);
    expect(heldSideways(270)).toBe(true);
    expect(heldSideways(0)).toBe(false);
    expect(heldSideways(180)).toBe(false);
    expect(heldSideways(null)).toBe(false);
    expect(isLandscape(wide(1))).toBe(true);
    expect(isLandscape(tall)).toBe(false);
    expect(isLandscape({ widthPx: 1000, heightPx: 1000 })).toBe(false);
    expect(isLandscape({ widthPx: 10, heightPx: 0 })).toBe(false);
  });
});

describe("adding to a room that has photos", () => {
  it("opens the camera for one more, keeping the room's photos", () => {
    expect(sessionWith([])).toBe(initialSession);
    expect(sessionWith([wide(1)])).toEqual({ current: { step: "camera" }, kept: [wide(1)] });
  });

  it("shows all three when the room has three, to retake one", () => {
    const three = [wide(1), wide(2), wide(3)];
    expect(sessionWith(three)).toEqual({ current: { step: "photos" }, kept: three });
  });
});

describe("a capture from Take photos", () => {
  it("is a package with no AR data whose pictures are marked as from the camera", () => {
    const capture = importedCapture("capture-1", "camera", keptFrames([wide(1), wide(2)]));
    expect(capture.origin).toBe("camera");
    expect(capture.files.keyframes).toEqual([
      { id: "k1", uri: "file:///p1.jpg" },
      { id: "k2", uri: "file:///p2.jpg" },
    ]);
    expect(capture.state.sensorLog).toEqual([
      JSON.stringify({ t: 0, source: "import", from: "camera", pictures: 2 }),
    ]);
    const uploaded = buildPackage(capture.state, {
      keyframes: { k1: "user/a.jpg", k2: "user/b.jpg" },
      sensorLog: "user/log.jsonl",
    });
    expect(uploaded.ar).toEqual({ tracking: "none", lidar: false, depth: false });
    const body = registerBody(
      capture,
      uploaded,
      { platform: "ios", tier: "standard", has_ar: false },
      "media-1",
    );
    expect(body.media[0]).toMatchObject({
      origin: "camera",
      width_px: 1600,
      height_px: 1200,
      has_ar_pose: false,
    });
  });
});
