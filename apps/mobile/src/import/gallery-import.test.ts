import { buildPackage } from "@/capture/package/recorder";
import { registerBody } from "@/capture/package/upload-capture";
import {
  checkSelection,
  frameTimesMs,
  importedCapture,
  type PickedItem,
  photoFrames,
} from "./gallery-import";

const photo = (n: number): PickedItem => ({
  uri: `file:///p${n}.jpg`,
  kind: "photo",
  widthPx: 4000,
  heightPx: 3000,
});
const video = (seconds: number): PickedItem => ({
  uri: "file:///room.mp4",
  kind: "video",
  widthPx: 1920,
  heightPx: 1080,
  durationMs: seconds * 1000,
});

describe("what was picked", () => {
  it("takes up to twenty photos, or one video", () => {
    expect(checkSelection([photo(1)])).toEqual({ ok: true, photos: [photo(1)] });
    expect(checkSelection(Array.from({ length: 20 }, (_, i) => photo(i))).ok).toBe(true);
    expect(checkSelection([video(20)])).toEqual({ ok: true, video: video(20) });
  });

  it("says plainly what it cannot use", () => {
    const problem = (items: PickedItem[]) => {
      const result = checkSelection(items);
      return result.ok ? null : result.problem;
    };
    expect(problem([])).toBe("nothing");
    expect(problem(Array.from({ length: 21 }, (_, i) => photo(i)))).toBe("tooManyPhotos");
    expect(problem([photo(1), video(20)])).toBe("photosAndVideo");
    expect(problem([video(20), video(20)])).toBe("severalVideos");
    expect(problem([video(3)])).toBe("videoTooShort");
    expect(problem([video(200)])).toBe("videoTooLong");
  });
});

describe("frames from a video", () => {
  it("are spread evenly, away from the first and last moments", () => {
    const times = frameTimesMs(20_000);
    expect(times).toHaveLength(20);
    expect(times[0]).toBe(500);
    expect(times[19]).toBe(19_500);
    const gaps = times.slice(1).map((t, i) => t - (times[i] ?? 0));
    expect(new Set(gaps)).toEqual(new Set([1000]));
  });

  it("are fewer for a short clip: two a second at most", () => {
    expect(frameTimesMs(5_000)).toHaveLength(10);
    expect(frameTimesMs(120_000)).toHaveLength(20);
  });
});

describe("an imported capture", () => {
  it("is a package with no AR data whose pictures are marked as from the gallery", () => {
    const capture = importedCapture("capture-1", "photos", photoFrames([photo(1), photo(2)]));
    expect(capture.files).toEqual({
      keyframes: [
        { id: "k1", uri: "file:///p1.jpg" },
        { id: "k2", uri: "file:///p2.jpg" },
      ],
      video: null,
      planes: null,
      sceneMesh: null,
      depth: null,
    });
    const uploaded = buildPackage(capture.state, {
      keyframes: { k1: "user/a.jpg", k2: "user/b.jpg" },
      sensorLog: "user/log.jsonl",
    });
    expect(uploaded.ar).toEqual({ tracking: "none", lidar: false, depth: false });
    expect(uploaded.keyframes.every((frame) => frame.pose === undefined)).toBe(true);
    expect(uploaded.video).toBeUndefined();
    expect(uploaded.planes).toBeUndefined();

    const body = registerBody(
      capture,
      uploaded,
      { platform: "android", tier: "low", has_ar: false },
      "media-1",
    );
    expect(body.media[0]).toMatchObject({
      origin: "gallery",
      width_px: 4000,
      height_px: 3000,
      has_ar_pose: false,
    });
  });

  it("keeps a video's frames in time order and says where they came from", () => {
    const frames = frameTimesMs(10_000).map((atMs, i) => ({
      uri: `file:///f${i}.jpg`,
      atMs,
      widthPx: 1920,
      heightPx: 1080,
    }));
    const capture = importedCapture("capture-2", "video", frames);
    expect(capture.files.keyframes).toHaveLength(20);
    expect(capture.state.sensorLog).toEqual([
      JSON.stringify({ t: 0, source: "import", from: "video", pictures: 20 }),
    ]);
  });

  it("needs at least one picture", () => {
    expect(() => importedCapture("capture-3", "photos", [])).toThrow();
  });
});
